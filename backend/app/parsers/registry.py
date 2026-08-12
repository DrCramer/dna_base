from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.parsers.excel_reader import read_workbook, row_value
from app.parsers.normalization import (
    SERVICE_LABELS,
    clean_text,
    is_service_label,
    json_safe,
    looks_like_decree_no,
    looks_like_rcsme_no,
    normalize_header,
    normalize_number,
    number_base,
    parse_date,
    parse_int,
)
from app.services.case_year import infer_case_year


REGISTRY_SHEET_NAME = "список объектов"

REGISTRY_HEADERS = [
    "№П/П",
    "№п/п",
    "Дата поступления в РЦСМЭ",
    "Дата постановления",
    "Следователь",
    "№ вх.",
    "№ постановления",
    "Комментарий (подробное описание объекта)",
    "№ присвоенный в в/ч № 522 ЦПООП Северо-Кавказского военного округа, г. Ростов-на-Дону",
    "Выделяем",
    "Коробка",
    "Кол-во пакетов на 1 объект",
    "№ рег РЦСМЭ",
    "Тип объекта (заполняется Брисевой А.С.)",
    "Ранее выделяли",
    "Не выделяли ранее",
    "Заполнение реестра (исполнитель)",
    "Пробоподготовка (фотофиксация)",
    "Пробоподготовка (помощь в фотофиксации)",
    "Пробоподготовка (отмывка)",
    "Пробоподготовка (помощь в отмывке)",
    "Пробоподготовка (отмывка) дата",
    "Пробоподготовка (размельчение кости, изъятие мягких тканей)",
    "Пробоподготовка (размельчение кости, изъятие мягких тканей) дата",
    "Пробоподготовка (размельчение кости на мельнице)",
    "Пробоподготовка (стаканы)",
    "Пробоподготовка  (размельчение на мельнице) дата",
    "Дата получения препарата ДНК",
    "Получение препарата ДНК (исполнитель)",
    "Метод получения препарата ДНК",
    "Метод измерения концентрации ДНК",
    "Дата измерения концентрации ДНК",
    "Оценка концентрации ДНК (исполнитель)",
    "Робот для раскапывания / ручной метод / Not applicable",
    "Комментарий",
    "Дата получения препарата ДНК",
    "Получение препарата ДНК (исполнитель)",
    "Метод получения препарата ДНК",
    "Комментарий",
    "Метод измерения концентрации ДНК",
    "Дата измерения концентрации ДНК",
    "Оценка концентрации ДНК (исполнитель)",
    "Робот для раскапывания / ручной метод / Not applicable",
    "Комментарий",
    "Дата постановки (PCR)",
    "Панель локусов",
    "Робот для раскапывания / ручной метод",
    "Нормализация PCR (исполнитель)",
    "Постановка PCR (исполнитель)",
    "Дата электрофореза",
    "Cеквенатор",
    "Робот для раскапывания / ручной метод",
    "Исполнитель 1",
    "Исполнитель 2",
    "Генотип",
    "Дата анализа фореза",
    "Исполнитель",
    "Дата анализа фореза",
    "Исполнитель",
    "Дата анализа фореза",
    "Исполнитель",
    "Дата анализа фореза",
    "Исполнитель",
    "Дата анализа фореза",
    "Исполнитель",
]


FIELD_ALIASES = {
    "registry_row_no": ["номер п п", "номерп п"],
    "intake_date": ["дата поступления в рцсмэ", "дата поступления в рцсме"],
    "decision_date": ["дата постановления"],
    "investigator": ["следователь"],
    "incoming_no": ["номер вх", "номер входящий"],
    "decree_no": ["номер постановления"],
    "object_description": [
        "комментарий подробное описание объекта",
        "описание комментарий",
        "описание объекта",
    ],
    "external_military_no": [
        "номер присвоенный в в ч номер 522 цпооп северо-кавказского военного округа г ростов-на-дону",
        "номер присвоенный в в ч номер 522 цпооп северо кавказского военного округа г ростов на дону",
        "номер в в ч номер 522",
        "номер в в ч номер522",
        "номер в в ч 522",
    ],
    "extraction_note": ["выделяем"],
    "box_no": ["коробка"],
    "packages_count": [
        "кол-во пакетов на 1 объект",
        "кол во пакетов на 1 объект",
        "количество пакетов на 1 объект",
    ],
    "rcsme_reg_no": ["номер рег рцсмэ", "номер рег рцсме"],
    "object_type": ["тип объекта заполняется брисевой а с"],
    "extracted_before": ["ранее выделяли"],
    "not_extracted_before": ["не выделяли ранее"],
    "registry_filled_by": [
        "заполнение реестра исполнитель",
        "заполнение реестра",
        "исполнитель заполнения реестра",
    ],
}


@dataclass
class RegistryPreview:
    sheet_name: str
    headers: list[str]
    rows: list[dict[str, Any]]
    skipped_rows: list[dict[str, Any]]
    warnings: list[str]
    party_control: dict[str, Any]


CONTROL_LABEL_TO_FIELD = {
    "фактическое количество постановлений:": "control_actual_decrees",
    "есть постановление, но нет объекта:": "control_decree_without_object",
    "есть объект, но нет постановления:": "control_object_without_decree",
    "неидентифицируемый ростовский номер:": "control_unidentified_rostov_no",
    "надо отозвать:": "control_need_recall",
    "отозваны:": "control_recalled",
}


def _header_indexes(header_row: list[Any]) -> dict[str, int]:
    normalized = {normalize_header(value): idx for idx, value in enumerate(header_row)}
    result: dict[str, int] = {}
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                result[field] = normalized[alias]
                break
    return result


def _row_raw(headers: list[str], row: list[Any]) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    cells: list[dict[str, Any]] = []
    for idx, header in enumerate(headers):
        name = clean_text(header) or f"column_{idx + 1}"
        value = json_safe(row_value(row, idx))
        cells.append({"index": idx + 1, "header": name, "value": value})
        raw[f"{name}__{idx + 1}"] = value
        if name not in raw:
            raw[name] = value
    raw["__cells"] = cells
    return raw


def _normalized_service_label(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    normalized = text.lower().replace("ё", "е")
    return normalized if normalized in SERVICE_LABELS else None


def _extract_control_from_skipped(skipped_rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for skipped in skipped_rows:
        raw = skipped.get("raw") or {}
        cells = raw.get("__cells")
        if not isinstance(cells, list):
            continue
        for index, cell in enumerate(cells):
            if not isinstance(cell, dict):
                continue
            label = _normalized_service_label(cell.get("value"))
            if not label:
                continue
            field = CONTROL_LABEL_TO_FIELD.get(label)
            if not field:
                continue
            values = [
                json_safe(next_cell.get("value"))
                for next_cell in cells[index + 1 :]
                if isinstance(next_cell, dict) and clean_text(next_cell.get("value"))
            ]
            result[field] = {
                "label": label,
                "row_number": skipped.get("row_number"),
                "values": values,
                "text": "; ".join(str(value) for value in values if value is not None) or None,
            }
    return result


def _raw_block(headers: list[str], row: list[Any], indexes: list[int], block: str) -> dict[str, Any]:
    cells = []
    for idx in indexes:
        header = clean_text(headers[idx - 1]) if idx - 1 < len(headers) else f"column_{idx}"
        cells.append({"index": idx, "header": header or f"column_{idx}", "value": json_safe(row_value(row, idx - 1))})
    return {"source": "registry_excel", "block": block, "columns": cells}


def _has_meaningful_values(raw_json: dict[str, Any]) -> bool:
    for cell in raw_json.get("columns", []):
        if isinstance(cell, dict) and clean_text(cell.get("value")):
            return True
    return False


def _event(
    table: str,
    block: str,
    data: dict[str, Any],
    headers: list[str],
    row: list[Any],
    indexes: list[int],
) -> dict[str, Any] | None:
    raw_json = _raw_block(headers, row, indexes, block)
    if not _has_meaningful_values(raw_json):
        return None
    return {"table": table, "block": block, "data": data, "raw_json": raw_json}


def _join_comment(*parts: str | None) -> str | None:
    values = [part for part in parts if part]
    return "; ".join(values) or None


def _find_header(headers: list[str], normalized_name: str, *, start: int = 0) -> int | None:
    for idx in range(max(start, 0), len(headers)):
        if normalize_header(headers[idx]) == normalized_name:
            return idx
    return None


def _find_headers(headers: list[str], normalized_name: str, *, start: int = 0) -> list[int]:
    return [
        idx
        for idx in range(max(start, 0), len(headers))
        if normalize_header(headers[idx]) == normalized_name
    ]


def _raw_indexes(start: int, length: int) -> list[int]:
    return [idx + 1 for idx in range(start, start + length)]


def _is_bad_analysis_performer(value: Any) -> bool:
    text = clean_text(value)
    if not text:
        return False
    normalized = text.lower().replace("ё", "е")
    if parse_date(value):
        return True
    blocked_values = {
        "ручной",
        "not applicable",
        "globalfiler",
        "globalfiltr",
        "identifier_plus",
        "identifiler_plus",
        "verifiler plus",
        "ngm_detect",
        "panGlobal plus".lower(),
        "попытка",
    }
    if normalized in blocked_values:
        return True
    return bool(text.isdigit())


def _analysis_pair_data(row: list[Any], date_idx: int, performer_idx: int | None) -> dict[str, Any] | None:
    analysis_date = parse_date(row_value(row, date_idx))
    performer = clean_text(row_value(row, performer_idx)) if performer_idx is not None else None
    if performer and _is_bad_analysis_performer(performer):
        performer = None
    if not analysis_date and not performer:
        return None
    return {
        "analysis_date": analysis_date,
        "performer": performer,
        "result_status": None,
        "comment": None,
    }


def _extract_stage_events(headers: list[str], row: list[Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    prep_blocks = [
        (
            "prep_photo",
            [18, 19],
            {
                "stage_type": "photo",
                "performer": clean_text(row_value(row, 17)),
                "assistant": clean_text(row_value(row, 18)),
                "event_date": None,
                "comment": None,
            },
        ),
        (
            "prep_washing",
            [20, 21, 22],
            {
                "stage_type": "washing",
                "performer": clean_text(row_value(row, 19)),
                "assistant": clean_text(row_value(row, 20)),
                "event_date": parse_date(row_value(row, 21)),
                "comment": None,
            },
        ),
        (
            "prep_soft_tissue",
            [23, 24],
            {
                "stage_type": "soft_tissue_grinding",
                "performer": clean_text(row_value(row, 22)),
                "assistant": None,
                "event_date": parse_date(row_value(row, 23)),
                "comment": None,
            },
        ),
        (
            "prep_mill_grinding",
            [25, 26, 27],
            {
                "stage_type": "mill_grinding",
                "performer": clean_text(row_value(row, 24)),
                "assistant": None,
                "event_date": parse_date(row_value(row, 26)),
                "comment": _join_comment(
                    f"Стаканы: {clean_text(row_value(row, 25))}" if clean_text(row_value(row, 25)) else None
                ),
            },
        ),
    ]
    for block, indexes, data in prep_blocks:
        item = _event("object_prep_events", block, data, headers, row, indexes)
        if item:
            events.append(item)

    extraction_blocks = [
        (
            "dna_extraction_1",
            [28, 29, 30, 31, 32, 33, 34, 35],
            {
                "extraction_no": 1,
                "extraction_date": parse_date(row_value(row, 27)),
                "performer": clean_text(row_value(row, 28)),
                "extraction_method": clean_text(row_value(row, 29)),
                "quant_method": clean_text(row_value(row, 30)),
                "quant_date": parse_date(row_value(row, 31)),
                "quant_performer": clean_text(row_value(row, 32)),
                "pipetting_method": clean_text(row_value(row, 33)),
                "comment": clean_text(row_value(row, 34)),
                "extraction_comment": None,
                "quant_comment": clean_text(row_value(row, 34)),
            },
        ),
        (
            "dna_extraction_2",
            [36, 37, 38, 39, 40, 41, 42, 43, 44],
            {
                "extraction_no": 2,
                "extraction_date": parse_date(row_value(row, 35)),
                "performer": clean_text(row_value(row, 36)),
                "extraction_method": clean_text(row_value(row, 37)),
                "quant_method": clean_text(row_value(row, 39)),
                "quant_date": parse_date(row_value(row, 40)),
                "quant_performer": clean_text(row_value(row, 41)),
                "pipetting_method": clean_text(row_value(row, 42)),
                "comment": _join_comment(clean_text(row_value(row, 38)), clean_text(row_value(row, 43))),
                "extraction_comment": clean_text(row_value(row, 38)),
                "quant_comment": clean_text(row_value(row, 43)),
            },
        ),
    ]
    for block, indexes, data in extraction_blocks:
        item = _event("dna_extractions", block, data, headers, row, indexes)
        if item:
            events.append(item)

    pcr_start = _find_header(headers, "дата постановки pcr")
    if pcr_start is None:
        pcr_start = 44
    pcr = _event(
        "pcr_events",
        "pcr",
        {
            "pcr_date": parse_date(row_value(row, pcr_start)),
            "locus_panel": clean_text(row_value(row, pcr_start + 1)),
            "pipetting_method": clean_text(row_value(row, pcr_start + 2)),
            "normalization_performer": clean_text(row_value(row, pcr_start + 3)),
            "pcr_performer": clean_text(row_value(row, pcr_start + 4)),
            "comment": None,
        },
        headers,
        row,
        _raw_indexes(pcr_start, 5),
    )
    if pcr:
        events.append(pcr)

    electrophoresis_start = _find_header(headers, "дата электрофореза", start=pcr_start + 5)
    if electrophoresis_start is None:
        electrophoresis_start = 49
    electrophoresis = _event(
        "electrophoresis_events",
        "electrophoresis",
        {
            "electrophoresis_date": parse_date(row_value(row, electrophoresis_start)),
            "sequencer": clean_text(row_value(row, electrophoresis_start + 1)),
            "pipetting_method": clean_text(row_value(row, electrophoresis_start + 2)),
            "performer_1": clean_text(row_value(row, electrophoresis_start + 3)),
            "performer_2": clean_text(row_value(row, electrophoresis_start + 4)),
            "genotype": clean_text(row_value(row, electrophoresis_start + 5)),
            "comment": None,
        },
        headers,
        row,
        _raw_indexes(electrophoresis_start, 6),
    )
    if electrophoresis:
        events.append(electrophoresis)

    genotype = clean_text(row_value(row, electrophoresis_start + 5))
    genotype_raw_index = electrophoresis_start + 6
    analysis_date_indexes = _find_headers(headers, "дата анализа фореза", start=electrophoresis_start + 6)
    analysis_written = 0
    for attempt_no, date_idx in enumerate(analysis_date_indexes, start=1):
        performer_idx = date_idx + 1 if normalize_header(row_value(headers, date_idx + 1)) == "исполнитель" else None
        analysis_data = _analysis_pair_data(row, date_idx, performer_idx)
        if not analysis_data:
            continue
        if analysis_written == 0:
            analysis_data["genotype"] = genotype
        analysis_data["attempt_no"] = attempt_no
        indexes = [date_idx + 1]
        if performer_idx is not None:
            indexes.append(performer_idx + 1)
        if analysis_written == 0 and genotype:
            indexes.append(genotype_raw_index)
        analysis = _event(
            "electrophoresis_analysis_events",
            f"electrophoresis_analysis_{attempt_no}",
            analysis_data,
            headers,
            row,
            indexes,
        )
        if analysis:
            events.append(analysis)
            analysis_written += 1

    if genotype and analysis_written == 0:
        analysis = _event(
            "electrophoresis_analysis_events",
            "electrophoresis_analysis_1",
            {
                "analysis_date": None,
                "performer": None,
                "result_status": None,
                "comment": None,
                "genotype": genotype,
                "attempt_no": 1,
            },
            headers,
            row,
            [genotype_raw_index],
        )
        if analysis:
            events.append(analysis)

    return events


def _is_real_object_row(row_map: dict[str, Any]) -> bool:
    if any(is_service_label(value) for value in row_map.values()):
        return False
    decree = row_map.get("decree_no")
    rcsme = row_map.get("rcsme_reg_no")
    return looks_like_decree_no(decree) or looks_like_rcsme_no(rcsme)


def _extract_object(row_number: int, row: list[Any], headers: list[str], indexes: dict[str, int]) -> dict[str, Any]:
    values = {field: row_value(row, idx) for field, idx in indexes.items()}
    decree_no = normalize_number(values.get("decree_no"))
    rcsme_reg_no = normalize_number(values.get("rcsme_reg_no"))
    return {
        "source_sheet_name": REGISTRY_SHEET_NAME,
        "source_row_number": row_number,
        "registry_row_no": clean_text(values.get("registry_row_no")),
        "intake_date": parse_date(values.get("intake_date")),
        "decision_date": parse_date(values.get("decision_date")),
        "investigator": clean_text(values.get("investigator")),
        "incoming_no": clean_text(values.get("incoming_no")),
        "decree_no": decree_no,
        "decree_no_base": number_base(decree_no),
        "object_description": clean_text(values.get("object_description")),
        "external_military_no": clean_text(values.get("external_military_no")),
        "extraction_note": clean_text(values.get("extraction_note")),
        "box_no": clean_text(values.get("box_no")),
        "packages_count": parse_int(values.get("packages_count")),
        "rcsme_reg_no": rcsme_reg_no,
        "rcsme_reg_no_base": number_base(rcsme_reg_no),
        "object_type": clean_text(values.get("object_type")),
        "extracted_before": clean_text(values.get("extracted_before")),
        "not_extracted_before": clean_text(values.get("not_extracted_before")),
        "registry_filled_by": clean_text(values.get("registry_filled_by")),
        "raw_registry_json": _row_raw(headers, row),
        "stage_events": _extract_stage_events(headers, row),
    }


def parse_registry(path: str | Path) -> RegistryPreview:
    workbook = read_workbook(path)
    if REGISTRY_SHEET_NAME not in workbook:
        raise ValueError(f"Не найден лист {REGISTRY_SHEET_NAME!r}")

    rows = workbook[REGISTRY_SHEET_NAME]
    if not rows:
        raise ValueError("Лист реестра пуст")

    header_row = rows[0]
    headers = [clean_text(value) or f"column_{idx + 1}" for idx, value in enumerate(header_row)]
    indexes = _header_indexes(header_row)
    missing = sorted(set(FIELD_ALIASES) - set(indexes))
    warnings = [f"Не найдены ожидаемые колонки: {', '.join(missing)}"] if missing else []
    parsed_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []

    for row_number, row in enumerate(rows[1:], start=2):
        extracted = _extract_object(row_number, row, headers, indexes)
        raw_has_values = any(str(value).strip() for value in extracted["raw_registry_json"].values() if value is not None)
        if not raw_has_values:
            continue
        if _is_real_object_row(extracted):
            parsed_rows.append(extracted)
        else:
            skipped_rows.append(
                {
                    "row_number": row_number,
                    "reason": "service_or_not_object",
                    "raw": extracted["raw_registry_json"],
                }
            )

    return RegistryPreview(
        sheet_name=REGISTRY_SHEET_NAME,
        headers=headers,
        rows=parsed_rows,
        skipped_rows=skipped_rows,
        warnings=warnings,
        party_control=_extract_control_from_skipped(skipped_rows),
    )


def registry_export_row(obj: Any) -> list[Any]:
    raw = obj.raw_registry_json or {}
    cells = raw.get("__cells")
    if isinstance(cells, list):
        by_index = {
            int(cell.get("index")): cell.get("value", "")
            for cell in cells
            if isinstance(cell, dict) and str(cell.get("index", "")).isdigit()
        }
        row = [by_index.get(idx, "") for idx in range(1, len(REGISTRY_HEADERS) + 1)]
    else:
        row = [raw.get(header, "") for header in REGISTRY_HEADERS]
    replacements = {
        1: obj.registry_row_no,
        2: obj.intake_date,
        3: obj.decision_date,
        4: obj.investigator,
        5: obj.incoming_no,
        6: obj.decree_no,
        7: obj.object_description,
        8: obj.external_military_no,
        9: obj.extraction_note,
        10: obj.box_no,
        11: obj.packages_count,
        12: obj.rcsme_reg_no,
        13: obj.object_type,
        14: obj.extracted_before,
        15: obj.not_extracted_before,
        16: obj.registry_filled_by,
    }
    for idx, value in replacements.items():
        if value is not None:
            row[idx] = value
    _apply_stage_export_values(row, getattr(obj, "stage_events", []) or [])
    return row


def _join_values(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        values = [clean_text(item) for item in value]
        return ", ".join(item for item in values if item) or None
    return clean_text(value)


def _performers_text(event: Any) -> str | None:
    performers = getattr(event, "performers", []) or []
    names = [clean_text(getattr(performer, "raw_name", None)) for performer in performers]
    return ", ".join(name for name in names if name) or None


def _detail(event: Any, name: str) -> Any:
    return getattr(event, name, None)


def _latest(events: list[Any], stage_type: str, attempt_no: int | None = None) -> Any | None:
    candidates = [
        event
        for event in events
        if getattr(event, "stage_type", None) == stage_type
        and not getattr(event, "is_cancelled", False)
        and (attempt_no is None or getattr(event, "attempt_no", None) == attempt_no)
    ]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda event: (
            getattr(event, "event_date", None) is not None,
            getattr(event, "event_date", None),
            getattr(event, "id", 0),
        ),
        reverse=True,
    )[0]


def _set(row: list[Any], index: int, value: Any) -> None:
    if value is not None:
        row[index] = value


def _apply_stage_export_values(row: list[Any], events: list[Any]) -> None:
    sample_prep = _latest(events, "sample_prep")
    if sample_prep:
        detail = _detail(sample_prep, "sample_prep_detail")
        _set(row, 17, _join_values(getattr(detail, "photo_performers", None)))
        _set(row, 18, _join_values(getattr(detail, "photo_assistants", None)))
        _set(row, 19, _join_values(getattr(detail, "washing_performers", None)))
        _set(row, 20, _join_values(getattr(detail, "washing_assistants", None)))
        _set(row, 21, getattr(detail, "washing_date", None) or getattr(sample_prep, "event_date", None))
        _set(row, 22, _join_values(getattr(detail, "bone_tissue_performers", None)))
        _set(row, 23, getattr(detail, "bone_tissue_date", None))

    milling = _latest(events, "milling")
    if milling:
        detail = _detail(milling, "milling_detail")
        _set(row, 24, _join_values(getattr(detail, "milling_performers", None)) or _performers_text(milling))
        _set(row, 25, getattr(detail, "cups", None))
        _set(row, 26, getattr(detail, "milling_date", None) or getattr(milling, "event_date", None))

    for attempt_no, base_index in ((1, 27), (2, 35)):
        dna = _latest(events, "dna_extraction", attempt_no)
        realtime = _latest(events, "realtime", attempt_no)
        if dna:
            detail = _detail(dna, "dna_extraction_detail")
            _set(row, base_index, getattr(detail, "extraction_date", None) or getattr(dna, "event_date", None))
            _set(row, base_index + 1, _performers_text(dna))
            _set(row, base_index + 2, getattr(detail, "extraction_method", None))
            _set(row, base_index + (7 if attempt_no == 1 else 3), getattr(dna, "comment", None))
        if realtime:
            detail = _detail(realtime, "realtime_detail")
            quant_offset = 3 if attempt_no == 1 else 4
            _set(row, base_index + quant_offset, getattr(detail, "quant_method", None))
            _set(row, base_index + quant_offset + 1, getattr(detail, "quant_date", None) or getattr(realtime, "event_date", None))
            _set(row, base_index + quant_offset + 2, getattr(detail, "quant_performer", None) or _performers_text(realtime))
            _set(row, base_index + quant_offset + 3, getattr(detail, "pipetting_method", None))
            _set(row, base_index + (7 if attempt_no == 1 else 8), getattr(detail, "comment", None))

    pcr = _latest(events, "pcr")
    if pcr:
        detail = _detail(pcr, "pcr_detail")
        _set(row, 44, getattr(detail, "pcr_date", None) or getattr(pcr, "event_date", None))
        _set(row, 45, getattr(detail, "locus_panel", None))
        _set(row, 46, getattr(detail, "pipetting_method", None))
        _set(row, 47, _join_values(getattr(detail, "normalization_performers", None)))
        _set(row, 48, _join_values(getattr(detail, "pcr_performers", None)) or _performers_text(pcr))

    electrophoresis = _latest(events, "electrophoresis")
    if electrophoresis:
        detail = _detail(electrophoresis, "electrophoresis_detail")
        performers = _join_values(getattr(detail, "performers", None)) or _performers_text(electrophoresis)
        performer_parts = [part.strip() for part in performers.split(",")] if performers else []
        _set(row, 49, getattr(detail, "electrophoresis_date", None) or getattr(electrophoresis, "event_date", None))
        _set(row, 50, getattr(detail, "sequencer", None))
        _set(row, 51, getattr(detail, "pipetting_method", None))
        _set(row, 52, performer_parts[0] if performer_parts else None)
        _set(row, 53, performer_parts[1] if len(performer_parts) > 1 else None)

    for attempt_no in range(1, 6):
        analysis = _latest(events, "analysis", attempt_no)
        if not analysis:
            continue
        detail = _detail(analysis, "analysis_detail")
        base_index = 55 + ((attempt_no - 1) * 2)
        _set(row, base_index, getattr(detail, "analysis_date", None) or getattr(analysis, "event_date", None))
        _set(row, base_index + 1, _performers_text(analysis))
