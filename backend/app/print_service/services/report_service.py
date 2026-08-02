from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


CSV_COLUMNS = [
    "Группа",
    "Столбец документов",
    "Столбец меток",
    "Порядок",
    "Номер документа",
    "Исходный файл",
    "Наносимая метка",
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
                    "Группа": entry.get("group", ""),
                    "Столбец документов": entry.get("group_column", ""),
                    "Столбец меток": entry.get("stamp_column", ""),
                    "Номер документа": entry.get("number", ""),
                    "Исходный файл": entry.get("matched_file") or "",
                    "Наносимая метка": entry.get("stamp_label") or "",
                    "Метка нанесена": "да" if entry.get("stamp_applied") else "нет",
                    "Страница документа": entry.get("pages") or "",
                    "Страница итогового PDF": entry.get("final_page") or entry.get("order", ""),
                    "Итоговый PDF": entry.get("result_pdf_name") or "",
                    "Статус сопоставления": entry.get("status", ""),
                    "Статус конвертации": entry.get("conversion_status", ""),
                    "Количество страниц": entry.get("pages") or "",
                    "Ширина страницы, мм": width,
                    "Высота страницы, мм": height,
                    "Предупреждения": " | ".join(entry.get("warnings") or []),
                    "Ошибка": entry.get("error") or "",
                }
            )
