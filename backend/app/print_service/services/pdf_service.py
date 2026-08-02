from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz
from pypdf import PdfReader, PdfWriter


POINT_TO_MM = 25.4 / 72


class PdfValidationError(ValueError):
    pass


def points_to_mm(value: float) -> float:
    return round(value * POINT_TO_MM, 1)


def page_label(width_mm: float, height_mm: float) -> str:
    short, long = sorted((width_mm, height_mm))
    orientation = "книжная" if height_mm >= width_mm else "альбомная"
    if abs(short - 210) <= 3 and abs(long - 297) <= 3:
        return f"A4, {orientation}"
    if abs(short - 216) <= 3 and abs(long - 279) <= 3:
        return f"Letter, {orientation}"
    return f"нестандартный размер, {orientation}"


def _page_has_visible_content(page: fitz.Page) -> bool:
    if page.get_text("text").strip():
        return True
    pixmap = page.get_pixmap(matrix=fitz.Matrix(0.15, 0.15), alpha=False)
    samples = pixmap.samples
    nonwhite_channels = sum(1 for channel in samples if channel < 245)
    return nonwhite_channels / max(len(samples), 1) > 0.001


def analyze_pdf(path: Path) -> dict[str, Any]:
    try:
        pymupdf_doc = fitz.open(path)
        reader = PdfReader(str(path))
    except Exception as exc:
        raise PdfValidationError(f"PDF не открывается: {path.name}") from exc
    if len(pymupdf_doc) != len(reader.pages):
        raise PdfValidationError(f"Некорректное количество страниц в PDF: {path.name}")
    pages: list[dict[str, Any]] = []
    for index, page in enumerate(pymupdf_doc, start=1):
        rect = page.rect
        width_mm = points_to_mm(rect.width)
        height_mm = points_to_mm(rect.height)
        pypdf_page = reader.pages[index - 1]
        rotate = int(pypdf_page.get("/Rotate", 0) or 0)
        visible = _page_has_visible_content(page)
        pages.append(
            {
                "index": index,
                "width_mm": width_mm,
                "height_mm": height_mm,
                "size_label": page_label(width_mm, height_mm),
                "orientation": "книжная" if height_mm >= width_mm else "альбомная",
                "visible": visible,
                "rotate": rotate,
                "media_box": [float(v) for v in pypdf_page.mediabox],
                "crop_box": [float(v) for v in pypdf_page.cropbox],
            }
        )
    pymupdf_doc.close()
    return {
        "path": str(path),
        "page_count": len(pages),
        "pages": pages,
        "empty_pages": [page["index"] for page in pages if not page["visible"]],
    }


def ensure_single_non_empty_page(analysis: dict[str, Any], source_name: str) -> None:
    if analysis["page_count"] != 1:
        raise PdfValidationError(
            f"Документ {source_name} преобразован в {analysis['page_count']} страницы. Сборка отменена."
        )
    if analysis["empty_pages"]:
        raise PdfValidationError(f"Документ {source_name} преобразован в пустую страницу.")


def reduce_to_single_page(pdf_path: Path, visible_page_index: int) -> None:
    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()
    writer.add_page(reader.pages[visible_page_index - 1])
    temporary_path = pdf_path.with_suffix(".single-page.pdf")
    with temporary_path.open("wb") as handle:
        writer.write(handle)
    temporary_path.replace(pdf_path)


def merge_pdfs(pdf_paths: list[Path], output_path: Path) -> dict[str, Any]:
    writer = PdfWriter()
    page_summaries: list[dict[str, Any]] = []
    for path in pdf_paths:
        reader = PdfReader(str(path))
        if len(reader.pages) != 1:
            raise PdfValidationError(f"PDF должен быть одностраничным: {path.name}")
        page = reader.pages[0]
        page_summaries.append(
            {
                "source": path.name,
                "media_box": [float(v) for v in page.mediabox],
                "crop_box": [float(v) for v in page.cropbox],
                "rotate": int(page.get("/Rotate", 0) or 0),
            }
        )
        writer.add_page(page)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as handle:
        writer.write(handle)
    return {
        "output": str(output_path),
        "page_count": len(pdf_paths),
        "pages": page_summaries,
        "size_bytes": output_path.stat().st_size,
    }
