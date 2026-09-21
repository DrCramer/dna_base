from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from app.parsers.excel_reader import read_workbook
from app.print_service.services.matching_service import canonical_match_key, contains_number_token, match_documents


class ExcelValidationError(ValueError):
    pass


def _document_contains(documents: list[dict[str, Any]], number: str) -> bool:
    canonical = canonical_match_key(number)
    return any(
        contains_number_token(canonical_match_key(Path(doc["original_name"]).stem), canonical)
        for doc in documents
    )


def _active_sheet_values(path: Path) -> tuple[str, list[list[Any]]]:
    if path.suffix.lower() == ".xlsx":
        try:
            workbook = load_workbook(path, read_only=True, data_only=True)
        except Exception as exc:
            raise ExcelValidationError("Не удалось прочитать Excel-файл") from exc
        sheet = workbook.active
        values = [list(row) for row in sheet.iter_rows(values_only=True)]
        title = sheet.title
        workbook.close()
        return title, values
    try:
        sheets = read_workbook(path)
    except Exception as exc:
        raise ExcelValidationError("Не удалось прочитать Excel-файл") from exc
    if not sheets:
        raise ExcelValidationError("В Excel-файле не найдено листов")
    return next(iter(sheets.items()))


def parse_excel_sequences(
    path: Path,
    documents: list[dict[str, Any]],
    *,
    excel_file_id: str = "excel_001",
    excel_file_name: str | None = None,
    include_file_in_title: bool = False,
) -> list[dict[str, Any]]:
    sheet_name, rows = _active_sheet_values(path)
    max_column = max((len(row) for row in rows), default=0)
    groups: list[dict[str, Any]] = []
    for column_index in range(1, max_column + 1):
        raw_values: list[str] = []
        for row in rows:
            value = row[column_index - 1] if column_index <= len(row) else None
            if value is None:
                continue
            text = str(value).strip()
            if text:
                raw_values.append(text)
        if not raw_values:
            continue

        column = get_column_letter(column_index)
        title = f"Столбец {column}"
        numbers = raw_values
        if len(raw_values) > 1 and not _document_contains(documents, raw_values[0]):
            later_matches = any(_document_contains(documents, value) for value in raw_values[1:])
            if later_matches:
                title = raw_values[0]
                numbers = raw_values[1:]

        if not numbers:
            continue
        display_title = f"{Path(excel_file_name).stem} · {title}" if include_file_in_title and excel_file_name else title
        groups.append(
            {
                "id": f"{excel_file_id}:{sheet_name}:col_{column}",
                "title": display_title,
                "column": column,
                "sheet": sheet_name,
                "excel_file_id": excel_file_id,
                "excel_file": excel_file_name or path.name,
                "sequence": "\n".join(numbers),
                "count": len(numbers),
            }
        )

    if not groups:
        raise ExcelValidationError("В Excel-файле не найдено ни одного столбца с номерами")
    return groups


def _match_groups(groups: list[dict[str, Any]], documents: list[dict[str, Any]]) -> dict[str, Any]:
    used_doc_ids: set[str] = set()
    blocking_errors: list[str] = []
    warnings: list[str] = []
    validated_groups: list[dict[str, Any]] = []

    for group in groups:
        validation = match_documents(group["sequence"], documents, entry_id_prefix=group["id"])
        validation["unused_documents"] = []
        for entry in validation["entries"]:
            if entry.get("doc_id"):
                used_doc_ids.add(entry["doc_id"])
        if validation["blocking_errors"]:
            blocking_errors.extend(
                f"{group['title']}: {error}" for error in validation["blocking_errors"]
            )
        warnings.extend(f"{group['title']}: {warning}" for warning in validation["warnings"])
        validated_groups.append({**group, "validation": validation})

    unused = [doc for doc in documents if doc["id"] not in used_doc_ids]
    if unused:
        warnings.append(f"Не используются в итоговых PDF: {len(unused)}")

    return {
        "mode": "excel",
        "groups": validated_groups,
        "unused_documents": unused,
        "warnings": warnings,
        "blocking_errors": blocking_errors,
        "can_build": len(blocking_errors) == 0,
        "total_groups": len(validated_groups),
        "total": sum(group["validation"]["total"] for group in validated_groups),
    }


def match_excel_groups(path: Path, documents: list[dict[str, Any]]) -> dict[str, Any]:
    groups = parse_excel_sequences(path, documents, excel_file_name=path.name)
    result = _match_groups(groups, documents)
    result["excel_files"] = [{"id": "excel_001", "name": path.name}]
    return result


def match_excel_files(files: list[dict[str, Any]], documents: list[dict[str, Any]]) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    include_file_in_title = len(files) > 1
    for item in files:
        groups.extend(
            parse_excel_sequences(
                Path(item["path"]),
                documents,
                excel_file_id=item["id"],
                excel_file_name=item["name"],
                include_file_in_title=include_file_in_title,
            )
        )
    if not groups:
        raise ExcelValidationError("В Excel-файлах не найдено ни одного столбца с номерами")
    result = _match_groups(groups, documents)
    result["excel_files"] = [{"id": item["id"], "name": item["name"]} for item in files]
    return result


def rematch_excel_groups(
    validation: dict[str, Any],
    ordered_sequences: dict[str, list[str]],
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    for group in validation.get("groups") or []:
        values = ordered_sequences.get(group["id"])
        sequence = "\n".join(values) if values is not None else group["sequence"]
        groups.append({key: value for key, value in group.items() if key != "validation"} | {
            "sequence": sequence,
            "count": len([line for line in sequence.splitlines() if line.strip()]),
        })
    result = _match_groups(groups, documents)
    result["excel_files"] = list(validation.get("excel_files") or [])
    return result
