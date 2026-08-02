from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import re
from typing import Any

from app.parsers.excel_reader import read_workbook
from app.parsers.normalization import (
    clean_text,
    normalize_header,
    normalize_lab_sample,
    normalize_number,
    number_base,
    parse_date,
    parse_float,
)


RT_ALIASES = {
    "well": ["well", "лунка"],
    "sample_name_raw": ["sample name", "sample", "образец", "имя образца"],
    "target": ["target name", "target", "gene", "мишень"],
    "ct": ["ct", "cт", "cq", "ct mean", "cт mean"],
    "quantity_ng_ul": ["quantity", "quantity ng ul", "concentration", "концентрация"],
    "mean_quantity_ng_ul": ["quantity mean", "mean quantity", "средняя концентрация"],
    "degradation_index": ["degradation index", "di"],
    "ipc_ct": ["ipcct", "ipc ct"],
    "result_flag": ["comments", "flags", "flag", "комментарии"],
}


@dataclass
class RtPreview:
    parser_type: str
    columns: list[str]
    rows: list[dict[str, Any]]
    sample_names: list[str]
    warnings: list[str]
    run_date: date | None = None
    quant_method: str | None = None
    aggregated_samples: list[dict[str, Any]] | None = None


def detect_rt_file(path: str | Path, source_filename: str | None = None) -> tuple[str, int]:
    data = Path(path).read_bytes()
    haystack = data[:200_000].decode("latin1", errors="ignore").lower()
    filename = (source_filename or Path(path).name).lower()
    if "abs quant" in filename or "abs quant" in haystack:
        return "abs_quant", 90
    score = 0
    for token in ["quantstudio", "applied biosystems", "sample name", "target name", "degradation index"]:
        if token in haystack:
            score += 20
    if score:
        return "abi_quantstudio", min(score, 100)
    return "generic_table", 30


def _map_columns(header: list[Any]) -> dict[str, int]:
    normalized = [normalize_header(value).replace(" ", "") for value in header]
    mapping: dict[str, int] = {}
    for field, aliases in RT_ALIASES.items():
        alias_norms = [normalize_header(alias).replace(" ", "") for alias in aliases]
        for idx, value in enumerate(normalized):
            if value in alias_norms:
                mapping[field] = idx
                break
    return mapping


def _display_header(value: Any, index: int) -> str:
    text = clean_text(value) or f"column_{index + 1}"
    return text.replace("Cт", "Ct").replace("cт", "ct")


def _find_table(rows: list[list[Any]]) -> tuple[list[Any], list[list[Any]], dict[str, int]] | None:
    for idx, row in enumerate(rows):
        mapping = _map_columns(row)
        if {"sample_name_raw", "target"} <= set(mapping):
            return row, rows[idx + 1 :], mapping
    return None


def _target_key(value: Any) -> str | None:
    text = normalize_header(value).replace("autosomal", "").replace("t ", " ").strip()
    text = re.sub(r"\s+", " ", text)
    compact = text.replace(" ", "")
    if "ipc" in compact:
        return "ipc"
    if "large" in compact or "long" in compact:
        return "long"
    if "small" in compact or "short" in compact:
        return "small"
    if compact in {"y", "ty"} or compact.endswith(" y"):
        return "y"
    return None


def _run_date_from_rows(rows: list[list[Any]]) -> date | None:
    for row in rows[:20]:
        for idx, value in enumerate(row):
            label = normalize_header(value)
            if "experiment run end time" in label and idx + 1 < len(row):
                parsed = _parse_run_datetime(row[idx + 1])
                if parsed:
                    return parsed
    return None


def _parse_run_datetime(value: Any) -> date | None:
    text = clean_text(value)
    if not text:
        return None
    match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if match:
        return parse_date(match.group(1))
    return parse_date(text)


def _run_date_from_filename(path: Path) -> date | None:
    name = path.name
    patterns = [
        r"(\d{2})[-_.](\d{2})[-_.](\d{4})",
        r"(\d{2})[-_.](\d{2})[-_.](\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, name)
        if not match:
            continue
        day, month, year = match.groups()
        if len(year) == 2:
            year = f"20{year}"
        parsed = parse_date(f"{day}.{month}.{year}")
        if parsed:
            return parsed
    return None


def _quant_method(path: Path, parser_type: str, rows: list[dict[str, Any]]) -> str | None:
    name = path.name.lower()
    if "abs quant" in name or parser_type == "abs_quant":
        return "Real Quant"
    if "0.5" in name or "0,5" in name:
        return "TRIO 0.5V"
    if any(_target_key(row.get("target")) in {"long", "small", "y"} for row in rows):
        return "TRIO"
    return None


def _row_from_mapping(row: list[Any], mapping: dict[str, int]) -> dict[str, Any]:
    def value(field: str) -> Any:
        idx = mapping.get(field)
        return row[idx] if idx is not None and idx < len(row) else None

    sample = normalize_number(value("sample_name_raw"))
    lab_sample = normalize_lab_sample(sample)
    target = clean_text(value("target"))
    quantity = parse_float(value("quantity_ng_ul"))
    mean_quantity = parse_float(value("mean_quantity_ng_ul"))
    return {
        "well": clean_text(value("well")),
        "sample_name_raw": clean_text(value("sample_name_raw")),
        "normalized_sample_name": sample,
        "sample_object_no": lab_sample.object_no,
        "sample_base": lab_sample.base or number_base(sample),
        "repeat_suffix": lab_sample.repeat_suffix,
        "target": target,
        "target_key": _target_key(target),
        "ct": parse_float(value("ct")),
        "cq": parse_float(value("ct")),
        "quantity_ng_ul": quantity,
        "mean_quantity_ng_ul": mean_quantity,
        "degradation_index": parse_float(value("degradation_index")),
        "ipc_ct": parse_float(value("ipc_ct")),
        "result_flag": clean_text(value("result_flag")),
        "raw_json": {str(k): v for k, v in enumerate(row, start=1)},
    }


def _is_lab_sample(value: str | None) -> bool:
    sample = normalize_lab_sample(value)
    return bool(sample.object_no and re.fullmatch(r"\d{1,8}-\d{1,4}", sample.object_no))


def _quantity(row: dict[str, Any]) -> float | None:
    value = row.get("quantity_ng_ul")
    return value if value is not None else row.get("mean_quantity_ng_ul")


def _round4(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def aggregate_rt_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        sample_name = row.get("normalized_sample_name")
        if not _is_lab_sample(sample_name):
            continue
        lab_sample = normalize_lab_sample(sample_name)
        key = lab_sample.normalized or sample_name
        item = grouped.setdefault(
            key,
            {
                "sample_name_raw": row.get("sample_name_raw"),
                "normalized_sample_name": lab_sample.normalized,
                "sample_object_no": lab_sample.object_no,
                "sample_base": lab_sample.base,
                "repeat_suffix": lab_sample.repeat_suffix,
                "long_quantity": None,
                "small_quantity": None,
                "y_quantity": None,
                "targets": {},
                "wells": [],
            },
        )
        if row.get("well") and row.get("well") not in item["wells"]:
            item["wells"].append(row.get("well"))
        target_key = row.get("target_key")
        if target_key in {"long", "small", "y"}:
            value = _round4(_quantity(row))
            item[f"{target_key}_quantity"] = value
            item["targets"][target_key] = {
                "target": row.get("target"),
                "quantity": value,
                "ct": _round4(row.get("ct") or row.get("cq")),
                "well": row.get("well"),
            }
    return list(grouped.values())


def _strings_fallback(path: Path, parser_type: str, display_path: Path | None = None) -> RtPreview:
    display_path = display_path or path
    data = path.read_bytes()
    text = data.decode("latin1", errors="ignore")
    tokens = re.findall(r"[A-Za-zА-Яа-я0-9_.:()/\\-]{2,}", text)
    samples = sorted(set(token for token in tokens if re.fullmatch(r"\d{2,8}-\d{1,4}", token)))[:200]
    columns = [
        "Well",
        "Sample Name",
        "Target Name",
        "Ct",
        "Quantity",
        "Quantity Mean",
        "Degradation Index",
        "IPCCT",
    ]
    rows = []
    for sample in samples:
        lab_sample = normalize_lab_sample(sample)
        rows.append(
            {
                "sample_name_raw": sample,
                "normalized_sample_name": sample,
                "sample_object_no": lab_sample.object_no,
                "sample_base": lab_sample.base or number_base(sample),
                "repeat_suffix": lab_sample.repeat_suffix,
            }
        )
    return RtPreview(
        parser_type=parser_type,
        columns=columns,
        rows=rows[:50],
        sample_names=samples,
        warnings=["Файл распознан по содержимому; табличное чтение недоступно, используйте ручной маппинг/CSV при необходимости."],
        run_date=_run_date_from_filename(display_path),
        quant_method=_quant_method(display_path, parser_type, rows),
        aggregated_samples=aggregate_rt_rows(rows),
    )


def parse_rt_preview(path: str | Path, manual_mapping: dict[str, str] | None = None, source_filename: str | None = None) -> RtPreview:
    path = Path(path)
    display_path = Path(source_filename or path.name)
    parser_type, _score = detect_rt_file(path, source_filename)
    try:
        workbook = read_workbook(path)
    except Exception:
        return _strings_fallback(path, parser_type, display_path)

    warnings: list[str] = []
    for sheet_name, rows in workbook.items():
        table = _find_table(rows)
        if not table:
            continue
        header, data_rows, mapping = table
        columns = [_display_header(value, idx) for idx, value in enumerate(header)]
        parsed_rows = []
        sample_names: list[str] = []
        for row in data_rows:
            parsed = _row_from_mapping(row, mapping)
            if not parsed["sample_name_raw"]:
                continue
            parsed["sheet_name"] = sheet_name
            parsed_rows.append(parsed)
            if parsed["normalized_sample_name"] and _is_lab_sample(parsed["normalized_sample_name"]):
                sample_names.append(parsed["normalized_sample_name"])
        run_date = _run_date_from_rows(rows) or _run_date_from_filename(display_path)
        quant_method = _quant_method(display_path, parser_type, parsed_rows)
        return RtPreview(
            parser_type=parser_type,
            columns=columns,
            rows=parsed_rows,
            sample_names=sorted(set(sample_names)),
            warnings=warnings,
            run_date=run_date,
            quant_method=quant_method,
            aggregated_samples=aggregate_rt_rows(parsed_rows),
        )

    fallback = _strings_fallback(path, parser_type, display_path)
    fallback.warnings.append("Не найдена строка заголовков Well/Sample Name/Target Name.")
    return fallback
