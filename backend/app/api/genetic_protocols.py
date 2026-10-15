import asyncio
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
from typing import Any
import zipfile
from xml.etree import ElementTree as ET

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, db_session, edit_user
from app.models import Employee, GeneticExamination, GeneticExaminationObject, GeneticExaminationRtRun, GeneticProtocolUpload, ProtocolStageProfile, User
from app.parsers.genetic_identity import genetic_key
from app.parsers.rt import parse_rt_preview
from app.parsers.work_protocol import parse_work_protocol_preview
from app.schemas.genetic_protocols import GeneticExcelApply, GeneticNumbersRequest, GeneticNumberInput, GeneticRtCommit
from app.services.audit import write_audit
from app.services.files import save_upload, upload_metadata
from app.services.genetic_protocols import apply_numbers, commit_rt, genetic_object_snapshots, preview_numbers, rt_samples
from app.services.protocol_resources import protocol_calculation_gate
from app.core.config import get_settings
from app.services.genetic_excel import excel_source_items, resolve_excel_items, excel_cells, selected_stage_patch

router = APIRouter(prefix="/protocols/genetic-examinations", tags=["genetic protocols"])
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def check_sample_names(rows: list[dict[str, Any]]) -> None:
    if any(len(str(row.get("sample_name_raw") or "")) > 255 or len(genetic_key(row.get("sample_name_raw"))) > 255 or "\0" in str(row.get("sample_name_raw") or "") for row in rows):
        raise HTTPException(status_code=400, detail="Номер образца не должен превышать 255 символов")


def json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return jsonable_encoder(value)


async def checked_upload(session: AsyncSession, upload_id: str, category: str, year: int, user: User) -> GeneticProtocolUpload:
    upload = await session.get(GeneticProtocolUpload, upload_id)
    if not upload or upload.owner_user_id != user.id or upload.category != category or upload.examination_year != year:
        raise HTTPException(status_code=404, detail="Предпросмотр файла не найден в текущем контексте")
    if upload.created_at < datetime.now(timezone.utc) - timedelta(hours=24):
        raise HTTPException(status_code=410, detail="Предпросмотр устарел. Загрузите файл заново.")
    return upload


def validate_archive(path: Path) -> None:
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            if sum(item.file_size for item in archive.infolist()) > 80 * 1024 * 1024 or len(archive.infolist()) > 2000:
                raise HTTPException(status_code=413, detail="Слишком большой объём распакованного Excel")


@router.post("/numbers/preview")
async def numbers_preview(payload: GeneticNumbersRequest, session: AsyncSession = Depends(db_session), _user: User = Depends(edit_user)):
    return await preview_numbers(session, payload)


@router.post("/numbers/apply")
async def numbers_apply(payload: GeneticNumbersRequest, session: AsyncSession = Depends(db_session), user: User = Depends(edit_user)):
    result = await apply_numbers(session, payload, user.id)
    await write_audit(session, user, "genetic_examination", None, "genetic_objects_imported", None, {"year": payload.examination_year, "added": result["added"], "existing": result["existing"]})
    await session.commit()
    return result


@router.get("/objects")
async def objects_list(examination_year: int = Query(ge=1900, le=2200), q: str = "", examination_no: str | None = None, limit: int = Query(default=100, ge=1, le=200), offset: int = Query(default=0, ge=0), session: AsyncSession = Depends(db_session), _user: User = Depends(current_user)):
    conditions = [GeneticExamination.examination_year == examination_year]
    if q:
        conditions.append(GeneticExaminationObject.display_name.ilike(f"%{q.strip()}%"))
    if examination_no:
        conditions.append(GeneticExamination.examination_no == examination_no)
    ids = list((await session.execute(select(GeneticExaminationObject.id).join(GeneticExamination, GeneticExamination.id == GeneticExaminationObject.examination_id).where(*conditions).order_by(GeneticExaminationObject.id).limit(limit).offset(offset))).scalars())
    return {"items": await genetic_object_snapshots(session, ids, examination_year), "limit": limit, "offset": offset}


@router.post("/excel/preview")
async def excel_preview(file: UploadFile = File(...), examination_year: int = Form(..., ge=1900, le=2200), session: AsyncSession = Depends(db_session), user: User = Depends(edit_user)):
    if len(Path(file.filename or "").name) > 255:
        raise HTTPException(status_code=400, detail="Слишком длинное имя файла")
    if Path(file.filename or "").suffix.lower() != ".xlsx":
        raise HTTPException(status_code=400, detail="Выберите Excel-протокол .xlsx")
    upload_id, digest, path = await save_upload(file, "genetic_excel", max_bytes=MAX_UPLOAD_BYTES)
    validate_archive(path)
    try:
        parsed = await protocol_calculation_gate.run(lambda: asyncio.to_thread(parse_work_protocol_preview, path, policy="genetic"))
    except (ValueError, KeyError, OSError, IndexError, ET.ParseError, zipfile.BadZipFile) as error:
        raise HTTPException(status_code=400, detail="Не удалось прочитать Excel-протокол") from error
    data = json_safe(asdict(parsed))
    check_sample_names(parsed.objects)
    if len(parsed.objects) > get_settings().protocol_max_objects:
        raise HTTPException(status_code=400, detail="В Excel слишком много объектов для одного протокола. Разделите состав.")
    source_items = excel_source_items(data)
    payload = GeneticNumbersRequest(examination_year=examination_year, items=[GeneticNumberInput(**item) for item in source_items]) if source_items else None
    if payload is None:
        raise HTTPException(status_code=400, detail="В файле не найдены объекты")
    preview = await preview_numbers(session, payload)
    upload = GeneticProtocolUpload(id=upload_id, category="excel", examination_year=examination_year, owner_user_id=user.id, source_filename=upload_metadata(path)["original_filename"], sha256=digest, parsed_json=data)
    session.add(upload)
    await session.commit()
    return {"upload_id": upload_id, "filename": upload.source_filename, **data, **preview}


async def excel_stage_settings(session: AsyncSession, data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    employees = list((await session.execute(select(Employee))).scalars())
    profiles = list((await session.execute(select(ProtocolStageProfile))).scalars())
    stages, warnings = [], []
    date_keys = {"dna_extraction": "extraction_date", "realtime": "quant_date", "pcr": "pcr_date", "electrophoresis": "electrophoresis_date"}
    kit_keys = {"dna_extraction": "extraction_method", "realtime": "quant_method", "pcr": "locus_panel"}
    for block in data["stage_blocks"]:
        stage_type = "dna_extraction" if block["stage_type"] == "extraction" else block["stage_type"]
        detail = block["detail_data"]
        kit = detail.get(kit_keys.get(stage_type, ""))
        if stage_type == "electrophoresis" and (detail.get("comment") or "").startswith("Набор: "):
            kit = detail["comment"][7:]
        matching = [profile for profile in profiles if profile.stage_type == stage_type and genetic_key(profile.name) == genetic_key(kit)] if kit else []
        performers = []
        for item in block["performers"]:
            name = item["raw_name"]
            matching_employees = [employee for employee in employees if genetic_key(name) in {genetic_key(employee.full_name), genetic_key(employee.short_name)}]
            employee_id = matching_employees[0].id if len(matching_employees) == 1 else None
            if employee_id is None:
                warnings.append(f"Исполнитель «{name}» не найден однозначно. Имя сохранено в документе.")
            performers.append({"employee_id": employee_id, "display_name": name, "role": item.get("role")})
        stages.append({"stage_type": stage_type, "enabled": True, "work_date": detail.get(date_keys[stage_type]), "profile_id": matching[0].id if len(matching) == 1 else None, "kit_name": kit, "sequencer_name": detail.get("sequencer"), "comment": detail.get("comment"), "performer_ids": [item["employee_id"] for item in performers if item["employee_id"]], "performers": performers, "settings": {"imported": True}})
    return stages, warnings


@router.post("/excel/apply")
async def excel_apply(payload: GeneticExcelApply, session: AsyncSession = Depends(db_session), user: User = Depends(edit_user)):
    upload = await checked_upload(session, payload.upload_id, "excel", payload.examination_year, user)
    data = upload.parsed_json
    resolved_items = resolve_excel_items(payload, data)
    result = await apply_numbers(session, GeneticNumbersRequest(examination_year=payload.examination_year, items=resolved_items), user.id)
    cells = []
    if "layout" in payload.selected_fields:
        cells = excel_cells(payload, data, resolved_items, result["object_ids"])
        from app.schemas.protocols import ProtocolImportedWell
        from app.services.protocol_import_layout import apply_imported_layouts
        from app.services.protocol_plate import build_protocol_layouts
        prepared = apply_imported_layouts(build_protocol_layouts(result["objects"]), [ProtocolImportedWell(**cell) for cell in cells], result["objects"])
        if cells:
            cells = [{"layout_key": key, "plate_index": plate["plate_index"], "well": well["well"], "kind": well["kind"], "source_id": well.get("object_id"), "label": well.get("label")} for key in ("source", "pcr") for plate in prepared[key]["plates"] for well in plate["wells"]]
    stages, warnings = await excel_stage_settings(session, data) if "stages" in payload.selected_fields else ([], [])
    stages = [selected_stage_patch(stage, payload.selected_stage_fields) for stage in stages]
    for stage in stages:
        stage["settings"].update({"source_filename": upload.source_filename, "upload_id": upload.id, "sha256": upload.sha256})
    result.update(imported_wells=cells, stages=stages, warnings=warnings, header={key: data.get(key) for key in ("protocol_date", "protocol_name", "protocol_no")} if "header" in payload.selected_fields else {})
    await write_audit(session, user, "genetic_examination", None, "genetic_excel_imported", None, {"year": payload.examination_year, "sha256": upload.sha256, "count": len(result["objects"])})
    await session.commit()
    return result


@router.post("/rt/preview")
async def rt_preview(files: list[UploadFile] = File(...), examination_year: int = Form(..., ge=1900, le=2200), object_ids: str = Form(...), session: AsyncSession = Depends(db_session), user: User = Depends(edit_user)):
    if not 1 <= len(files) <= 10:
        raise HTTPException(status_code=400, detail="За один импорт допускается до 10 RT-файлов")
    try:
        ids = [int(value) for value in object_ids.split(",") if value]
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Некорректный состав объектов") from error
    objects = await genetic_object_snapshots(session, ids, examination_year)
    output = []
    seen_digests = set()
    for file in files:
        if len(Path(file.filename or "").name) > 255:
            raise HTTPException(status_code=400, detail="Слишком длинное имя файла")
        if Path(file.filename or "").suffix.lower() not in {".xls", ".xlsx", ".csv"}:
            raise HTTPException(status_code=400, detail="RT: поддерживаются .xls, .xlsx и .csv")
        upload_id, digest, path = await save_upload(file, "genetic_rt", max_bytes=MAX_UPLOAD_BYTES)
        validate_archive(path)
        parsed = await protocol_calculation_gate.run(lambda: asyncio.to_thread(parse_rt_preview, path, source_filename=file.filename))
        if len(parsed.rows) > 10000:
            raise HTTPException(status_code=413, detail="В RT-файле больше 10000 строк")
        check_sample_names(parsed.rows)
        if not any(row.get("target_key") for row in parsed.rows):
            raise HTTPException(status_code=400, detail="Не найдена количественная таблица мишеней RT. Проверьте формат файла.")
        data = json_safe(asdict(parsed))
        duplicate = digest in seen_digests or bool((await session.execute(select(GeneticExaminationRtRun.id).where(GeneticExaminationRtRun.sha256 == digest, GeneticExaminationRtRun.examination_year == examination_year))).first())
        seen_digests.add(digest)
        upload = GeneticProtocolUpload(id=upload_id, category="rt", examination_year=examination_year, owner_user_id=user.id, source_filename=upload_metadata(path)["original_filename"], sha256=digest, parsed_json=data)
        session.add(upload)
        output.append({"upload_id": upload_id, "filename": upload.source_filename, "sha256": digest, "duplicate": duplicate, "warnings": parsed.warnings, "samples": rt_samples(data["rows"], objects)})
    await session.commit()
    return {"files": output}


@router.post("/rt/commit")
async def rt_commit(payload: GeneticRtCommit, session: AsyncSession = Depends(db_session), user: User = Depends(edit_user)):
    if len(set(payload.upload_ids)) != len(payload.upload_ids):
        raise HTTPException(status_code=400, detail="Повтор файла в задании")
    uploads = [await checked_upload(session, upload_id, "rt", payload.examination_year, user) for upload_id in payload.upload_ids]
    result = await commit_rt(session, payload, uploads, user.id)
    await write_audit(session, user, "genetic_examination", None, "genetic_rt_imported", None, {"year": payload.examination_year, "run_ids": result["run_ids"], "matched": result["matched"]})
    await session.commit()
    return result
