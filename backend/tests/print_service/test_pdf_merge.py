from pathlib import Path

import fitz
import pytest
from pypdf import PdfReader, PdfWriter

from app.print_service.services.pdf_service import PdfValidationError, analyze_pdf, merge_pdfs, reduce_to_single_page


def write_pdf(path: Path, width: float, height: float, rotate: int = 0, pages: int = 1) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=width, height=height)
        if rotate:
            page.rotate(rotate)
    with path.open("wb") as handle:
        writer.write(handle)


def test_merge_preserves_different_page_sizes_and_rotation(tmp_path):
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    output = tmp_path / "merged.pdf"
    write_pdf(first, 595, 842)
    write_pdf(second, 612, 792, rotate=90)

    result = merge_pdfs([first, second], output)
    reader = PdfReader(str(output))

    assert result["page_count"] == 2
    assert len(reader.pages) == 2
    assert list(reader.pages[0].mediabox) == list(PdfReader(str(first)).pages[0].mediabox)
    assert list(reader.pages[1].mediabox) == list(PdfReader(str(second)).pages[0].mediabox)
    assert int(reader.pages[1].get("/Rotate")) == 90


def test_merge_rejects_multipage_pdf(tmp_path):
    source = tmp_path / "multi.pdf"
    output = tmp_path / "merged.pdf"
    write_pdf(source, 595, 842, pages=2)
    with pytest.raises(PdfValidationError):
        merge_pdfs([source], output)


def test_reduce_pdf_with_one_visible_and_one_blank_page(tmp_path):
    source = tmp_path / "with-blank-tail.pdf"
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text((72, 72), "visible page")
    document.new_page(width=595, height=842)
    document.save(source)
    document.close()

    analysis = analyze_pdf(source)
    visible_pages = [page["index"] for page in analysis["pages"] if page["visible"]]
    assert analysis["page_count"] == 2
    assert visible_pages == [1]

    reduce_to_single_page(source, visible_pages[0])
    reduced = PdfReader(str(source))
    assert len(reduced.pages) == 1
    assert [float(value) for value in reduced.pages[0].mediabox] == [0.0, 0.0, 595.0, 842.0]
