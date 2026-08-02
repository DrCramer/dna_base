from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
from typing import Any


SERVICE_LABELS = {
    "фактическое количество постановлений:",
    "есть постановление, но нет объекта:",
    "есть объект, но нет постановления:",
    "неидентифицируемый ростовский номер:",
    "надо отозвать:",
    "отозваны:",
}


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\xa0", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text or None


def normalize_header(value: Any) -> str:
    text = clean_text(value) or ""
    text = text.lower().replace("ё", "е")
    text = text.replace("№", "номер")
    text = re.sub(r"[()\\/.,:;]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_number(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    text = text.replace("—", "-").replace("–", "-").replace("−", "-")
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"\s+", "", text)
    match = re.fullmatch(r"(\d{1,8}-\d{1,4})([A-Za-zА-Яа-я*]+)", text)
    if match:
        suffix = match.group(2).replace("Х", "x").replace("х", "x").lower()
        text = f"{match.group(1)}{suffix}"
    return text


def number_base(value: Any) -> str | None:
    text = normalize_number(value)
    if not text:
        return None
    match = re.search(r"\d+", text)
    return match.group(0) if match else None


@dataclass(frozen=True)
class LabSampleNumber:
    raw: str | None
    normalized: str | None
    object_no: str | None
    base: str | None
    repeat_suffix: str | None


def normalize_lab_sample(value: Any) -> LabSampleNumber:
    """Normalize lab sample IDs like 1201-1x to object number 1201-1."""
    normalized = normalize_number(value)
    if not normalized:
        return LabSampleNumber(None, None, None, None, None)
    match = re.fullmatch(r"(\d{1,8}-\d{1,4})([A-Za-zА-Яа-я*]+)?", normalized)
    if not match:
        return LabSampleNumber(normalized, normalized, normalized, number_base(normalized), None)
    object_no = match.group(1)
    suffix = match.group(2)
    if suffix:
        suffix = suffix.replace("Х", "x").replace("х", "x").lower()
        normalized = f"{object_no}{suffix}"
    return LabSampleNumber(normalized, normalized, object_no, number_base(object_no), suffix)


def extract_lab_samples_from_text(value: Any) -> list[LabSampleNumber]:
    text = clean_text(value)
    if not text:
        return []
    found: list[LabSampleNumber] = []
    seen: set[str] = set()
    for match in re.finditer(r"(?<!\d)(\d{1,8}\s*[-–—−]\s*\d{1,4}[A-Za-zА-Яа-я*]?)(?!\d)", text):
        sample = normalize_lab_sample(match.group(1))
        key = sample.normalized
        if key and key not in seen:
            seen.add(key)
            found.append(sample)
    return found


def extract_party_no(filename: Any) -> str | None:
    text = clean_text(Path(str(filename)).name)
    if not text:
        return None
    lowered = text.lower().replace("ё", "е")
    patterns = [
        r"(?:партия|партии|парт\.?)\s*[-№#:]?\s*(\d{1,6})",
        r"(\d{1,6})\s*(?:партия|партии|парт\.?)",
        r"№\s*(\d{1,6})\s*(?:реестр|реест|registry)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return match.group(1)
    stem = Path(text).stem
    match = re.match(r"\s*(\d{1,6})(?:\D|$)", stem)
    return match.group(1) if match else None


def looks_like_registry_row_no(value: Any) -> bool:
    text = clean_text(value)
    return bool(text and re.fullmatch(r"\d+", text))


def looks_like_decree_no(value: Any) -> bool:
    text = normalize_number(value)
    return bool(text and re.fullmatch(r"\d{2,8}-\d{2,4}", text))


def looks_like_rcsme_no(value: Any) -> bool:
    text = normalize_number(value)
    return bool(text and re.fullmatch(r"\d{2,8}-\d{1,4}", text))


def is_service_label(value: Any) -> bool:
    text = clean_text(value)
    return bool(text and text.lower().replace("ё", "е") in SERVICE_LABELS)


def parse_int(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return int(Decimal(text.replace(",", ".")))
    except (InvalidOperation, ValueError):
        return None


def parse_float(value: Any) -> float | None:
    text = clean_text(value)
    if not text or text.lower() in {"undetermined", "not applicable", "n/a"}:
        return None
    try:
        return float(Decimal(text.replace(",", ".")))
    except (InvalidOperation, ValueError):
        return None


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and value > 0:
        # Excel's 1900 date system, including the historic leap-year bug.
        return date(1899, 12, 30) + timedelta(days=int(value))
    text = clean_text(value)
    if not text:
        return None
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    if re.fullmatch(r"\d+(\.0)?", text):
        return parse_date(float(text))
    return None


def json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value
