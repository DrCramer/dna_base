from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


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


def _mapping_numbers(entry: dict[str, Any]) -> tuple[str, str]:
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
    return str(source_number), str(assigned_number)


def write_number_mapping_xlsx(entries: list[dict[str, Any]], output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Сопоставление"
    parts: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        pdf_name = str(entry.get("pdf_name") or entry.get("result_pdf_name") or "")
        parts.setdefault(pdf_name, []).append(entry)

    # Границы блоков совпадают с итоговыми PDF, в том числе для неполных партий.
    multiple_parts = sum(bool(name) for name in parts) > 1
    mapping_header_row = 2 if multiple_parts else 1
    sheet.freeze_panes = f"A{mapping_header_row + 1}"
    headers = ("Исходный номер", "Присвоенный номер")
    if multiple_parts:
        mapping_widths = ([28, 28, 4] * len(parts))[:-1]
        sheet.row_dimensions[1].height = 32
        for index, part_entries in enumerate(parts.values()):
            column = index * 3 + 1
            first = part_entries[0]
            label = f"Партия {first['party_no']}" if first.get("party_no") else first.get("group") or f"Часть {index + 1}"
            sheet.merge_cells(start_row=1, start_column=column, end_row=1, end_column=column + 1)
            title = sheet.cell(row=1, column=column, value=f"{label} · документов: {len(part_entries)}")
            title.data_type = "s"
            title.font = Font(bold=True, color="203238")
            title.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            for offset, header in enumerate(headers):
                sheet.cell(row=2, column=column + offset, value=header)
            for row, entry in enumerate(part_entries, start=3):
                for offset, number in enumerate(_mapping_numbers(entry)):
                    sheet.cell(row=row, column=column + offset, value=number)
    else:
        mapping_widths = [28, 28]
        sheet.append(headers)
        for entry in entries:
            sheet.append(_mapping_numbers(entry))

    details = workbook.create_sheet("Детали")
    details.freeze_panes = "A2"
    details.append(["Исходный номер", "Присвоенный номер", "Файл DOCX", "PDF", "Позиция в PDF"])
    for entry in entries:
        details.append(
            [
                *_mapping_numbers(entry),
                str(entry.get("matched_docx") or entry.get("matched_file") or ""),
                str(entry.get("pdf_name") or entry.get("result_pdf_name") or ""),
                entry.get("pdf_position") or entry.get("final_page") or entry.get("order") or "",
            ]
        )

    header_fill = PatternFill(fill_type="solid", fgColor="DCEAEC")
    for current, header_row, widths in ((sheet, mapping_header_row, mapping_widths), (details, 1, (28, 28, 44, 36, 18))):
        for cell in current[header_row]:
            if cell.value is None:
                continue
            cell.font = Font(bold=True, color="203238")
            cell.fill = header_fill
            cell.alignment = Alignment(vertical="center")
        for row in current.iter_rows(min_row=header_row + 1):
            for cell in row:
                cell.number_format = "@"
                cell.alignment = Alignment(vertical="top")
        for column_index, width in enumerate(widths, start=1):
            current.column_dimensions[get_column_letter(column_index)].width = width
        if current is not sheet or not multiple_parts:
            current.auto_filter.ref = f"A1:{get_column_letter(len(widths))}{max(1, current.max_row)}"
    workbook.save(output_path)
    workbook.close()
    return len(entries)
