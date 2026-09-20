from __future__ import annotations

import unicodedata
from collections import defaultdict
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


def canonical_match_key(value: str) -> str:
    return normalize_text(value).replace("/", "_")


def parse_sequence(sequence: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line_number, raw in enumerate(sequence.splitlines(), start=1):
        original = raw.strip()
        canonical = canonical_match_key(original)
        if not canonical:
            continue
        items.append(
            {
                "line": line_number,
                "number": original,
                "raw": original,
                "source_number_original": original,
                "source_number_canonical": canonical,
            }
        )
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


def _occurrence_error(number: str, occurrences: int, matches: int) -> str:
    def noun(count: int, one: str, few: str, many: str) -> str:
        mod10 = count % 10
        mod100 = count % 100
        if mod10 == 1 and mod100 != 11:
            return one
        if 2 <= mod10 <= 4 and not 12 <= mod100 <= 14:
            return few
        return many

    if matches == 0:
        return (
            f"Для номера {number} указано {occurrences} "
            f"{noun(occurrences, 'запись', 'записи', 'записей')}, документы не найдены."
        )
    if occurrences > matches:
        record_word = noun(occurrences, "запись", "записи", "записей")
        found = (
            "найден только 1 документ"
            if matches == 1
            else f"найдено только {matches} {noun(matches, 'документ', 'документа', 'документов')}"
        )
        return f"Для номера {number} указано {occurrences} {record_word}, {found}."
    return (
        f"Для номера {number} найдено {matches} "
        f"{noun(matches, 'документ', 'документа', 'документов')}. Нужно уточнить соответствие."
    )


def match_documents(
    sequence: str,
    documents: list[dict[str, Any]],
    *,
    entry_id_prefix: str = "entry",
) -> dict[str, Any]:
    items = parse_sequence(sequence)
    entries: list[dict[str, Any]] = []
    warnings: list[str] = []
    blocking_errors: list[str] = []
    canonical_names = {doc["id"]: canonical_match_key(_stem(doc["original_name"])) for doc in documents}
    items_by_key: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for order, item in enumerate(items, start=1):
        items_by_key[item["source_number_canonical"]].append((order, item))

    assignments: dict[int, dict[str, Any]] = {}
    group_errors: dict[int, str] = {}
    group_diagnostics: dict[int, list[str]] = {}
    missing_orders: set[int] = set()
    for canonical, occurrences in items_by_key.items():
        matches = [doc for doc in documents if contains_number_token(canonical_names[doc["id"]], canonical)]
        if len(matches) == len(occurrences):
            assignments.update(
                (order, doc)
                for (order, _item), doc in zip(occurrences, matches, strict=True)
            )
            continue
        display_number = occurrences[0][1]["source_number_original"]
        error = _occurrence_error(display_number, len(occurrences), len(matches))
        candidate_signature = diagnostic_signature(canonical)
        diagnostic_matches = [
            doc
            for doc in documents
            if contains_number_token(diagnostic_signature(canonical_names[doc["id"]]), candidate_signature)
            and not contains_number_token(canonical_names[doc["id"]], canonical)
        ]
        for order, _item in occurrences:
            group_errors[order] = error
            if not matches:
                missing_orders.add(order)
            if diagnostic_matches:
                group_diagnostics[order] = [doc["original_name"] for doc in diagnostic_matches[:3]]

    occurrence_counts: dict[str, int] = defaultdict(int)
    for order, item in enumerate(items, start=1):
        canonical = item["source_number_canonical"]
        occurrence_counts[canonical] += 1
        number = item["source_number_original"]
        entry = {
            "entry_id": f"{entry_id_prefix}_{order:06d}",
            "order": order,
            "line": item["line"],
            "number": number,
            "source_number_original": number,
            "source_number_canonical": canonical,
            "occurrence_index": occurrence_counts[canonical],
            "matched_file": None,
            "matched_docx": None,
            "doc_id": None,
            "status": "Готов",
            "blocking": False,
            "warnings": [],
            "error": "",
            "pages": None,
            "page_size": "",
            "conversion_status": "Ожидает",
        }
        if order in group_errors:
            entry["status"] = "Не найден" if order in missing_orders else "Ошибка"
            entry["blocking"] = True
            entry["error"] = group_errors[order]
            if order in group_diagnostics:
                names = ", ".join(group_diagnostics[order])
                entry["warnings"].append(
                    "Возможное совпадение: похожие кириллические и латинские символы. "
                    f"Проверьте файл: {names}"
                )
        else:
            doc = assignments[order]
            entry["matched_file"] = doc["original_name"]
            entry["matched_docx"] = doc["original_name"]
            entry["doc_id"] = doc["id"]
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
