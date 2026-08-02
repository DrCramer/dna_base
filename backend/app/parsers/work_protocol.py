from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.parsers.excel_reader import read_workbook, row_value
from app.parsers.normalization import clean_text, normalize_lab_sample, parse_date


SERVICE_SAMPLES = {"ladder", "pc", "nc", "к+", "к-", "positive", "negative"}


@dataclass
class ProtocolStageBlock:
    stage_type: str
    title: str
    detail_data: dict[str, Any]
    performers: list[dict[str, Any]]


@dataclass
class WorkProtocolPreview:
    protocol_title: str | None
    protocol_no: str | None
    protocol_name: str | None
    objects: list[dict[str, Any]]
    plate_cells: list[dict[str, Any]]
    stage_blocks: list[ProtocolStageBlock]
    warnings: list[str]


def _value(rows: list[list[Any]], row: int, col: int) -> Any:
    if row < 0 or row >= len(rows):
        return ""
    return row_value(rows[row], col)


def _text(rows: list[list[Any]], row: int, col: int) -> str | None:
    return clean_text(_value(rows, row, col))


def _date_value(rows: list[list[Any]], row: int, col: int) -> str | None:
    value = parse_date(_value(rows, row, col))
    return value.isoformat() if value else None


def _performers(*names: str | None, role: str = "performer") -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name in names:
        if name:
            result.append({"raw_name": name, "role": role})
    return result


def _stage_blocks_from_unified(rows: list[list[Any]]) -> list[ProtocolStageBlock]:
    blocks: list[ProtocolStageBlock] = []
    extraction_date = _date_value(rows, 3, 1)
    extraction_method = _text(rows, 4, 1)
    extraction_performers = [_text(rows, 5, 1), _text(rows, 6, 1)]
    if extraction_date or extraction_method or any(extraction_performers):
        blocks.append(
            ProtocolStageBlock(
                stage_type="extraction",
                title="Выделение из протокола плашки",
                detail_data={"extraction_date": extraction_date, "extraction_method": extraction_method},
                performers=_performers(*extraction_performers, role="dna_extraction"),
            )
        )

    rt_date = _date_value(rows, 3, 4)
    rt_method = _text(rows, 4, 4)
    rt_performers = [_text(rows, 5, 4), _text(rows, 6, 4)]
    if rt_date or rt_method or any(rt_performers):
        blocks.append(
            ProtocolStageBlock(
                stage_type="realtime",
                title="RealTime из протокола плашки",
                detail_data={"quant_date": rt_date, "quant_method": rt_method, "pipetting_method": "Ручной"},
                performers=_performers(*rt_performers, role="quant"),
            )
        )

    pcr_date = _date_value(rows, 3, 7)
    pcr_panel = _text(rows, 4, 7)
    pcr_performers = [_text(rows, 5, 7), _text(rows, 6, 7)]
    if pcr_date or pcr_panel or any(pcr_performers):
        blocks.append(
            ProtocolStageBlock(
                stage_type="pcr",
                title="ПЦР из протокола плашки",
                detail_data={"pcr_date": pcr_date, "locus_panel": pcr_panel},
                performers=_performers(*pcr_performers, role="pcr"),
            )
        )

    electrophoresis_date = _date_value(rows, 3, 10)
    electrophoresis_kit = _text(rows, 4, 10)
    electrophoresis_performer = _text(rows, 5, 10)
    sequencer = _text(rows, 6, 10)
    if electrophoresis_date or electrophoresis_kit or electrophoresis_performer or sequencer:
        blocks.append(
            ProtocolStageBlock(
                stage_type="electrophoresis",
                title="Электрофорез из протокола плашки",
                detail_data={
                    "electrophoresis_date": electrophoresis_date,
                    "sequencer": sequencer,
                    "pipetting_method": "Ручной",
                    "comment": f"Набор: {electrophoresis_kit}" if electrophoresis_kit else None,
                },
                performers=_performers(electrophoresis_performer, role="performer_1"),
            )
        )
    return blocks


def _stage_blocks_from_pcr(rows: list[list[Any]]) -> list[ProtocolStageBlock]:
    blocks: list[ProtocolStageBlock] = []
    pcr_date = _date_value(rows, 3, 1)
    pcr_panel = _text(rows, 4, 1)
    pcr_performers = [_text(rows, 5, 1), _text(rows, 6, 1)]
    if pcr_date or pcr_panel or any(pcr_performers):
        blocks.append(
            ProtocolStageBlock(
                stage_type="pcr",
                title="ПЦР из протокола плашки",
                detail_data={"pcr_date": pcr_date, "locus_panel": pcr_panel},
                performers=_performers(*pcr_performers, role="pcr"),
            )
        )
    electrophoresis_date = _date_value(rows, 3, 7)
    electrophoresis_kit = _text(rows, 4, 7)
    electrophoresis_performer = _text(rows, 5, 7)
    sequencer = _text(rows, 6, 7)
    if electrophoresis_date or electrophoresis_kit or electrophoresis_performer or sequencer:
        blocks.append(
            ProtocolStageBlock(
                stage_type="electrophoresis",
                title="Электрофорез из протокола плашки",
                detail_data={
                    "electrophoresis_date": electrophoresis_date,
                    "sequencer": sequencer,
                    "pipetting_method": "Ручной",
                    "comment": f"Набор: {electrophoresis_kit}" if electrophoresis_kit else None,
                },
                performers=_performers(electrophoresis_performer, role="performer_1"),
            )
        )
    return blocks


def _extract_plate_cells(rows: list[list[Any]], start_row: int) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row_index in range(start_row, min(len(rows), start_row + 16)):
        row = rows[row_index]
        row_label = clean_text(row_value(row, 0))
        if row_label and row_label.strip().upper() not in set("ABCDEFGH"):
            continue
        for col_index, cell in enumerate(row[1:13], start=1):
            text = clean_text(cell)
            if not text:
                continue
            lab_sample = normalize_lab_sample(text)
            well = f"{row_label}{col_index}" if row_label else None
            is_service = text.lower() in SERVICE_SAMPLES
            identity = f"service:{well}:{text.lower()}" if is_service else lab_sample.normalized
            if identity in seen:
                continue
            seen.add(identity)
            cells.append(
                {
                    "sample_name_raw": text,
                    "normalized_sample_name": lab_sample.normalized if not is_service else None,
                    "sample_object_no": lab_sample.object_no if not is_service else None,
                    "sample_base": lab_sample.base,
                    "repeat_suffix": lab_sample.repeat_suffix,
                    "well": well,
                    "is_service": is_service,
                }
            )
    return cells


def _extract_plate_objects(rows: list[list[Any]], start_row: int) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for cell in _extract_plate_cells(rows, start_row):
        if cell.get("is_service") or not cell.get("normalized_sample_name") or not cell.get("sample_object_no"):
            continue
        objects.append({key: value for key, value in cell.items() if key != "is_service"})
    return objects


def _objects_from_input_sheet(rows: list[list[Any]]) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows[1:]:
        text = clean_text(row_value(row, 1))
        if not text or text.lower() in SERVICE_SAMPLES:
            continue
        lab_sample = normalize_lab_sample(text)
        if not lab_sample.normalized or not lab_sample.object_no or lab_sample.normalized in seen:
            continue
        seen.add(lab_sample.normalized)
        objects.append(
            {
                "sample_name_raw": text,
                "normalized_sample_name": lab_sample.normalized,
                "sample_object_no": lab_sample.object_no,
                "sample_base": lab_sample.base,
                "repeat_suffix": lab_sample.repeat_suffix,
                "well": None,
            }
        )
    return objects


def parse_work_protocol_preview(path: str | Path) -> WorkProtocolPreview:
    workbook = read_workbook(path)
    warnings: list[str] = []
    rows = workbook.get("Единая_плашка_A4") or []
    stage_blocks: list[ProtocolStageBlock] = []
    objects: list[dict[str, Any]] = []
    plate_cells: list[dict[str, Any]] = []
    protocol_title = None
    protocol_no = None
    protocol_name = None
    if rows:
        protocol_title = _text(rows, 0, 0)
        protocol_no = _text(rows, 1, 4)
        protocol_name = _text(rows, 1, 6)
        stage_blocks.extend(_stage_blocks_from_unified(rows))
        plate_cells = _extract_plate_cells(rows, 9)
        objects = [{key: value for key, value in cell.items() if key != "is_service"} for cell in plate_cells if not cell.get("is_service") and cell.get("normalized_sample_name") and cell.get("sample_object_no")]

    if not objects and workbook.get("Ввод_объектов"):
        objects = _objects_from_input_sheet(workbook["Ввод_объектов"])
        warnings.append("Объекты взяты из листа Ввод_объектов.")

    pcr_rows = workbook.get("PCR") or []
    if pcr_rows and not stage_blocks:
        protocol_title = protocol_title or _text(pcr_rows, 0, 0)
        protocol_no = protocol_no or _text(pcr_rows, 1, 4)
        protocol_name = protocol_name or _text(pcr_rows, 1, 5)
        stage_blocks.extend(_stage_blocks_from_pcr(pcr_rows))
        if not objects:
            plate_cells = _extract_plate_cells(pcr_rows, 17)
            objects = [{key: value for key, value in cell.items() if key != "is_service"} for cell in plate_cells if not cell.get("is_service") and cell.get("normalized_sample_name") and cell.get("sample_object_no")]
    elif pcr_rows:
        # The PCR sheet can carry a separate PCR/EF setup; keep it as extra blocks
        # only if the unified sheet did not already provide PCR/electrophoresis.
        existing = {block.stage_type for block in stage_blocks}
        for block in _stage_blocks_from_pcr(pcr_rows):
            if block.stage_type not in existing:
                stage_blocks.append(block)

    if not objects:
        warnings.append("В протоколе не найдены номера объектов.")
    if not stage_blocks:
        warnings.append("В протоколе не найдены этапы для заполнения.")

    return WorkProtocolPreview(
        protocol_title=protocol_title,
        protocol_no=protocol_no,
        protocol_name=protocol_name,
        objects=objects,
        plate_cells=plate_cells,
        stage_blocks=stage_blocks,
        warnings=warnings,
    )
