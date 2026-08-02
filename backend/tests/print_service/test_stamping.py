from pathlib import Path

import fitz
from pypdf import PdfReader, PdfWriter

from app.print_service.services.matching_service import match_documents
from app.print_service.services.stamping_service import (
    StampingValidationError,
    apply_stamping_to_validation,
    normalize_stamp_style,
    parse_label_text,
    stamp_pdf,
)


def write_pdf(path: Path, width: float = 595, height: float = 842, rotate: int = 0) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=width, height=height)
    if rotate:
        page.rotate(rotate)
    with path.open("wb") as handle:
        writer.write(handle)


def docs(*names):
    return [
        {"id": f"doc_{index}", "original_name": name, "path": f"input/doc_{index}.docx"}
        for index, name in enumerate(names, start=1)
    ]


def stamp_config(text: str, **overrides):
    config = {
        "enabled": True,
        "text": text,
        "reject_duplicates": False,
        "allow_skip": False,
        "style": {},
    }
    config.update(overrides)
    return config


def test_parse_label_text_keeps_ready_values_and_ignores_blank_lines():
    labels = parse_label_text("\ufeff 6528-2026 \r\n\n№ 6529-2026\nРег. 6604-2026")
    assert labels == ["6528-2026", "№ 6529-2026", "Рег. 6604-2026"]


def test_parse_label_text_rejects_control_characters():
    try:
        parse_label_text("6528-2026\nbad\x00value")
    except StampingValidationError as exc:
        assert "нулевой" in str(exc)
    else:
        raise AssertionError("control character was accepted")


def test_stamping_validation_preserves_order_and_does_not_generate_numbers():
    validation = match_documents(
        "ее5968\nее6032\nнн2832",
        docs("Документ_ее5968.docx", "Документ_ее6032.docx", "Документ_нн2832.docx"),
    )
    result = apply_stamping_to_validation(validation, stamp_config("6528-2026\n6529-2026\n6531-2026"))
    assert result["can_build"] is True
    assert [entry["stamp_label"] for entry in result["entries"]] == [
        "6528-2026",
        "6529-2026",
        "6531-2026",
    ]


def test_stamping_validation_blocks_count_mismatch():
    validation = match_documents(
        "ее5968\nее6032\nнн2832",
        docs("Документ_ее5968.docx", "Документ_ее6032.docx", "Документ_нн2832.docx"),
    )
    result = apply_stamping_to_validation(validation, stamp_config("6528-2026\n6529-2026"))
    assert result["can_build"] is False
    assert "Не совпадает количество" in result["blocking_errors"][-1]


def test_stamping_validation_allows_duplicates_and_skip():
    validation = match_documents(
        "ее5968\nее6032\nнн2832",
        docs("Документ_ее5968.docx", "Документ_ее6032.docx", "Документ_нн2832.docx"),
    )
    result = apply_stamping_to_validation(
        validation,
        stamp_config("6528-2026\n6528-2026\nSKIP", allow_skip=True),
    )
    assert result["can_build"] is True
    assert result["stamping"]["summary"]["duplicate_count"] == 1
    assert result["stamping"]["summary"]["skipped"] == 1
    assert result["entries"][2]["stamp_skip"] is True


def test_stamp_pdf_preserves_page_geometry_and_source_file(tmp_path):
    source = tmp_path / "converted.pdf"
    output = tmp_path / "stamped.pdf"
    write_pdf(source, width=612, height=792, rotate=90)
    before_bytes = source.read_bytes()
    before = PdfReader(str(source)).pages[0]

    stamp_pdf(
        source,
        output,
        "6528-2026",
        {
            "corner": "top_left",
            "margin_x_mm": 10,
            "margin_y_mm": 8,
            "font_size": 12,
            "bold": False,
            "white_background": True,
            "border": True,
        },
    )

    after = PdfReader(str(output)).pages[0]
    assert source.read_bytes() == before_bytes
    assert list(after.mediabox) == list(before.mediabox)
    assert list(after.cropbox) == list(before.cropbox)
    assert int(after.get("/Rotate", 0) or 0) == 90
    document = fitz.open(output)
    try:
        assert "6528-2026" in document[0].get_text("text")
    finally:
        document.close()


def test_stamp_pdf_ascii_label_uses_compact_builtin_font(tmp_path):
    source = tmp_path / "converted.pdf"
    output = tmp_path / "stamped.pdf"
    write_pdf(source)
    stamp_pdf(
        source,
        output,
        "6528-2026",
        {
            "corner": "top_left",
            "margin_x_mm": 10,
            "margin_y_mm": 8,
            "font_size": 12,
            "bold": False,
            "white_background": False,
            "border": False,
        },
    )
    assert output.stat().st_size < 20_000


def test_stamp_pdf_supports_russian_text(tmp_path):
    source = tmp_path / "converted.pdf"
    output = tmp_path / "stamped.pdf"
    write_pdf(source)
    stamp_pdf(
        source,
        output,
        "Рег. 6604-2026",
        {
            "corner": "top_left",
            "margin_x_mm": 10,
            "margin_y_mm": 8,
            "font_size": 12,
            "bold": False,
            "white_background": False,
            "border": False,
        },
    )
    document = fitz.open(output)
    try:
        assert "Рег. 6604-2026" in document[0].get_text("text")
    finally:
        document.close()


def test_stamp_pdf_supports_left_90_rotation(tmp_path):
    source = tmp_path / "converted.pdf"
    output = tmp_path / "stamped.pdf"
    write_pdf(source)
    style = normalize_stamp_style(
        {
            "corner": "top_left",
            "rotation": "left_90",
            "margin_x_mm": 3,
            "margin_y_mm": 3,
            "font_size": 12,
            "bold": False,
            "white_background": True,
            "border": True,
        }
    )

    stamp_pdf(source, output, "6528-2026", style)

    document = fitz.open(output)
    try:
        assert "6528-2026" in document[0].get_text("text")
        spans = [
            span
            for block in document[0].get_text("dict")["blocks"]
            if block.get("type") == 0
            for line in block["lines"]
            for span in line["spans"]
            if span["text"] == "6528-2026"
        ]
        assert spans
        assert spans[0]["bbox"][1] < 18
        assert spans[0]["bbox"][0] >= 3 * 72 / 25.4
    finally:
        document.close()
