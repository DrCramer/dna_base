from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill


CSV_COLUMNS = [
    "ID записи",
    "Группа",
    "Столбец документов",
    "Столбец меток",
    "Порядок",
    "Номер документа",
    "Исходный номер",
    "Канонический номер",
    "Номер повтора",
    "Исходный файл",
    "Наносимая метка",
    "Присвоенный номер",
    "Метка нанесена",
    "Страница документа",
    "Страница итогового PDF",
    "Итоговый PDF",
    "Статус сопоставления",
    "Статус конвертации",
    "Количество страниц",
    "Ширина страницы, мм",
    "Высота страницы, мм",
    "Предупреждения",
    "Ошибка",
]


def write_csv_report(entries: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, delimiter=";")
        writer.writeheader()
        for entry in entries:
            width = ""
            height = ""
            analysis = entry.get("pdf_analysis")
            if analysis and analysis.get("pages"):
                width = analysis["pages"][0]["width_mm"]
                height = analysis["pages"][0]["height_mm"]
            writer.writerow(
                {
                    "Порядок": entry.get("order", ""),
                    "ID записи": entry.get("entry_id", ""),
                    "Группа": entry.get("group", ""),
                    "Столбец документов": entry.get("group_column", ""),
                    "Столбец меток": entry.get("stamp_column", ""),
                    "Номер документа": entry.get("number", ""),
                    "Исходный номер": entry.get("source_number_original") or entry.get("number", ""),
                    "Канонический номер": entry.get("source_number_canonical", ""),
                    "Номер повтора": entry.get("occurrence_index", ""),
                    "Исходный файл": entry.get("matched_docx") or entry.get("matched_file") or "",
                    "Наносимая метка": entry.get("stamp_label") or "",
                    "Присвоенный номер": entry.get("assigned_number") or entry.get("stamp_label") or "",
                    "Метка нанесена": "да" if entry.get("stamp_applied") else "нет",
                    "Страница документа": entry.get("pages") or "",
                    "Страница итогового PDF": entry.get("pdf_position") or entry.get("final_page") or entry.get("order", ""),
                    "Итоговый PDF": entry.get("pdf_name") or entry.get("result_pdf_name") or "",
                    "Статус сопоставления": entry.get("status", ""),
                    "Статус конвертации": entry.get("conversion_status", ""),
                    "Количество страниц": entry.get("pages") or "",
                    "Ширина страницы, мм": width,
                    "Высота страницы, мм": height,
                    "Предупреждения": " | ".join(entry.get("warnings") or []),
                    "Ошибка": entry.get("error") or "",
                }
            )


def write_number_mapping_xlsx(entries: list[dict[str, Any]], output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Сопоставление"
    sheet.freeze_panes = "A2"
    sheet.append(["Исходный номер", "Присвоенный номер"])

    for entry in entries:
        source_number = (
            entry.get("source_number_original")
            or entry.get("external_military_no")
            or entry.get("number")
            or ""
        )
        assigned_number = (
            entry.get("assigned_number")
            or entry.get("stamp_label")
            or entry.get("rcsme_reg_no")
            or entry.get("decree_no")
            or ""
        )
        sheet.append([str(source_number), str(assigned_number)])

    details = workbook.create_sheet("Детали")
    details.freeze_panes = "A2"
    details.append(["Исходный номер", "Присвоенный номер", "Файл DOCX", "PDF", "Позиция в PDF"])
    for entry in entries:
        details.append(
            [
                str(entry.get("source_number_original") or entry.get("external_military_no") or entry.get("number") or ""),
                str(entry.get("assigned_number") or entry.get("stamp_label") or entry.get("rcsme_reg_no") or entry.get("decree_no") or ""),
                str(entry.get("matched_docx") or entry.get("matched_file") or ""),
                str(entry.get("pdf_name") or entry.get("result_pdf_name") or ""),
                entry.get("pdf_position") or entry.get("final_page") or entry.get("order") or "",
            ]
        )

    header_fill = PatternFill(fill_type="solid", fgColor="DCEAEC")
    for current, widths in ((sheet, (28, 28)), (details, (28, 28, 44, 36, 18))):
        for cell in current[1]:
            cell.font = Font(bold=True, color="203238")
            cell.fill = header_fill
            cell.alignment = Alignment(vertical="center")
        for row in current.iter_rows(min_row=2):
            for cell in row:
                cell.number_format = "@"
                cell.alignment = Alignment(vertical="top")
        for column_index, width in enumerate(widths, start=1):
            current.column_dimensions[chr(64 + column_index)].width = width
        current.auto_filter.ref = f"A1:{chr(64 + len(widths))}{max(1, current.max_row)}"
    workbook.save(output_path)
    workbook.close()
    return len(entries)
