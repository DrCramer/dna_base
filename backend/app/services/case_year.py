from __future__ import annotations

from datetime import date
import re
from typing import Any

from app.parsers.normalization import clean_text, normalize_number

VALID_CASE_YEAR_MIN = 1900
VALID_CASE_YEAR_MAX = 2200


def normalize_case_year(value: Any) -> int | None:
    if value in (None, ''):
        return None
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    return year if VALID_CASE_YEAR_MIN <= year <= VALID_CASE_YEAR_MAX else None


def case_year_from_decree_no(value: Any) -> int | None:
    text = normalize_number(value) or clean_text(value)
    if not text:
        return None
    match = re.search(r'(?:^|-)((?:19|20|21)\d{2})$', text)
    if not match:
        return None
    return normalize_case_year(match.group(1))


def infer_case_year(*, decision_date: date | None = None, decree_no: Any = None, fallback: int | None = None) -> int | None:
    return case_year_from_decree_no(decree_no) or (decision_date.year if decision_date else None) or normalize_case_year(fallback)
