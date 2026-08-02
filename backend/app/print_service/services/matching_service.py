from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Any


CONFUSABLE_TO_LATIN = str.maketrans(
    {
        "а": "a",
        "е": "e",
        "о": "o",
        "р": "p",
        "с": "c",
        "х": "x",
        "у": "y",
        "к": "k",
        "м": "m",
        "т": "t",
        "н": "h",
        "в": "b",
    }
)


def normalize_text(value: str) -> str:
    value = value.replace("\ufeff", "").replace("\u00a0", " ").strip()
    return unicodedata.normalize("NFC", value).lower()


def diagnostic_signature(value: str) -> str:
    return normalize_text(value).translate(CONFUSABLE_TO_LATIN)


def parse_sequence(sequence: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line_number, raw in enumerate(sequence.splitlines(), start=1):
        number = normalize_text(raw)
        if not number:
            continue
        items.append({"line": line_number, "number": number, "raw": raw.strip()})
    return items


def _stem(original_name: str) -> str:
    return normalize_text(Path(original_name).stem)


def _is_word_char(value: str) -> bool:
    return value.isalnum()


def contains_number_token(haystack: str, needle: str) -> bool:
    start = haystack.find(needle)
    while start != -1:
        end = start + len(needle)
        before_ok = start == 0 or not _is_word_char(haystack[start - 1])
        after_ok = end == len(haystack) or not _is_word_char(haystack[end])
        if before_ok and after_ok:
            return True
        start = haystack.find(needle, start + 1)
    return False


def match_documents(sequence: str, documents: list[dict[str, Any]]) -> dict[str, Any]:
    items = parse_sequence(sequence)
    entries: list[dict[str, Any]] = []
    warnings: list[str] = []
    blocking_errors: list[str] = []
    normalized_names = {doc["id"]: _stem(doc["original_name"]) for doc in documents}
    used_doc_ids: list[str] = []

    first_seen: dict[str, int] = {}
    duplicate_lines: dict[str, list[int]] = {}
    for item in items:
        number = item["number"]
        if number in first_seen:
            duplicate_lines.setdefault(number, [first_seen[number]]).append(item["line"])
        else:
            first_seen[number] = item["line"]

    for order, item in enumerate(items, start=1):
        number = item["number"]
        matches = [doc for doc in documents if contains_number_token(normalized_names[doc["id"]], number)]
        candidate_signature = diagnostic_signature(number)
        diagnostic_matches = [
            doc
            for doc in documents
            if contains_number_token(diagnostic_signature(normalized_names[doc["id"]]), candidate_signature)
            and not contains_number_token(normalized_names[doc["id"]], number)
        ]
        entry = {
            "order": order,
            "line": item["line"],
            "number": number,
            "matched_file": None,
            "doc_id": None,
            "status": "Готов",
            "blocking": False,
            "warnings": [],
            "error": "",
            "pages": None,
            "page_size": "",
            "conversion_status": "Ожидает",
        }
        if number in duplicate_lines:
            entry["status"] = "Ошибка"
            entry["blocking"] = True
            entry["error"] = f"Номер повторяется в строках {', '.join(map(str, duplicate_lines[number]))}"
        elif len(matches) == 0:
            entry["status"] = "Не найден"
            entry["blocking"] = True
            entry["error"] = "Подходящий DOCX не найден"
            if diagnostic_matches:
                names = ", ".join(doc["original_name"] for doc in diagnostic_matches[:3])
                entry["warnings"].append(
                    "Возможное совпадение: похожие кириллические и латинские символы. "
                    f"Проверьте файл: {names}"
                )
        elif len(matches) > 1:
            entry["status"] = "Ошибка"
            entry["blocking"] = True
            entry["error"] = "Найдено несколько подходящих DOCX"
            entry["warnings"].append(", ".join(doc["original_name"] for doc in matches))
        else:
            doc = matches[0]
            entry["matched_file"] = doc["original_name"]
            entry["doc_id"] = doc["id"]
            used_doc_ids.append(doc["id"])
        entries.append(entry)

    doc_usage: dict[str, list[int]] = {}
    for entry in entries:
        if entry["doc_id"]:
            doc_usage.setdefault(entry["doc_id"], []).append(entry["order"])
    for entry in entries:
        if entry["doc_id"] and len(doc_usage[entry["doc_id"]]) > 1:
            entry["status"] = "Ошибка"
            entry["blocking"] = True
            entry["error"] = (
                "Один DOCX подходит нескольким номерам: "
                + ", ".join(map(str, doc_usage[entry["doc_id"]]))
            )

    for entry in entries:
        if entry["blocking"]:
            blocking_errors.append(f"{entry['number']} — {entry['error']}")
        elif entry["warnings"]:
            warnings.extend(entry["warnings"])

    unused = [
        doc
        for doc in documents
        if doc["id"] not in {entry["doc_id"] for entry in entries if entry["doc_id"]}
    ]
    if unused:
        warnings.append(f"Не используются в итоговом PDF: {len(unused)}")
    return {
        "entries": entries,
        "unused_documents": unused,
        "warnings": warnings,
        "blocking_errors": blocking_errors,
        "can_build": len(blocking_errors) == 0 and len(entries) > 0,
        "total": len(entries),
    }
