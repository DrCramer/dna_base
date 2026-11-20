import re
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import distinct, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from app.api.deps import current_user, db_session
from app.models import Party, RegistryObject, StageEvent, User
from app.services.export import build_registry_workbook
from app.services.rcsme_lookup import (
    MAX_FILE_BYTES, MAX_NUMBERS, RcsmeLookupResult, RcsmeLookupRow,
    build_rcsme_workbook, lookup_rcsme, parse_lookup_numbers,
)


router = APIRouter(prefix="/exports", tags=["exports"])
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post("/rcsme/preview", response_model=RcsmeLookupResult)
async def preview_rcsme_lookup(
    numbers: str = Form(default=""),
    case_year: int | None = Form(default=None, ge=1900, le=2200),
    file: UploadFile | None = File(default=None),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    if file is not None and numbers.strip():
        raise HTTPException(status_code=422, detail="Загрузите файл или вставьте список, но не оба сразу.")
    content = await file.read(MAX_FILE_BYTES + 1) if file is not None else b""
    try:
        ordered, duplicates = await run_in_threadpool(
            parse_lookup_numbers, numbers, filename=(file.filename or "") if file is not None else "", content=content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await lookup_rcsme(session, ordered, duplicates, case_year)


@router.post("/rcsme.xlsx")
async def export_rcsme_lookup(
    rows: list[RcsmeLookupRow] = Body(min_length=1, max_length=MAX_NUMBERS),
    _user: User = Depends(current_user),
):
    return Response(
        await run_in_threadpool(build_rcsme_workbook, rows),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="rcsme-matches.xlsx"'},
    )


STAGE_ALIASES = {
    "registration": "registration",
    "регистрация": "registration",
    "sample_prep": "sample_prep",
    "пробоподготовка": "sample_prep",
    "milling": "milling",
    "измельчение": "milling",
    "dna_extraction": "dna_extraction",
    "выделение": "dna_extraction",
    "realtime": "realtime",
    "real time": "realtime",
    "pcr": "pcr",
    "пцр": "pcr",
    "electrophoresis": "electrophoresis",
    "электрофорез": "electrophoresis",
    "analysis": "analysis",
    "анализ": "analysis",
}


def _parse_int_tokens(value: str | None) -> list[int]:
    if not value:
        return []
    result: list[int] = []
    for token in re.split(r"[\s,;]+", value.strip()):
        if not token.isdigit():
            continue
        number = int(token)
        if number not in result:
            result.append(number)
    return result


def _parse_text_tokens(value: str | None) -> list[str]:
    if not value:
        return []
    result: list[str] = []
    for token in re.split(r"[\s,;]+", value.strip()):
        normalized = token.strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _canonical_stage_type(value: str | None) -> str | None:
    if not value:
        return None
    return STAGE_ALIASES.get(value.strip().lower())


def _apply_export_filters(
    stmt: Any,
    *,
    q: str | None,
    party_no: str | None,
    party_ids: str | None,
    object_ids: str | None,
    object_nos: str | None,
    year: int | None,
    stage_type: str | None,
    include_archived: bool,
    only_problematic: bool,
):
    stmt = stmt.outerjoin(Party, Party.id == RegistryObject.party_id)
    if not include_archived:
        stmt = stmt.where(
            RegistryObject.status != "archived",
            or_(Party.id.is_(None), Party.status != "archived"),
        )
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                RegistryObject.rcsme_reg_no.ilike(needle),
                RegistryObject.party_no.ilike(needle),
                RegistryObject.decree_no.ilike(needle),
                RegistryObject.external_military_no.ilike(needle),
                RegistryObject.investigator.ilike(needle),
                RegistryObject.box_no.ilike(needle),
                RegistryObject.object_description.ilike(needle),
            )
        )
    if party_no:
        stmt = stmt.where(RegistryObject.party_no == party_no.strip())
    if party_ids is not None:
        parsed_party_ids = _parse_int_tokens(party_ids)
        stmt = stmt.where(RegistryObject.party_id.in_(parsed_party_ids) if parsed_party_ids else false())
    if object_ids is not None:
        parsed_object_ids = _parse_int_tokens(object_ids)
        stmt = stmt.where(RegistryObject.id.in_(parsed_object_ids) if parsed_object_ids else false())
    if object_nos is not None:
        parsed_object_nos = _parse_text_tokens(object_nos)
        stmt = stmt.where(RegistryObject.rcsme_reg_no.in_(parsed_object_nos) if parsed_object_nos else false())
    if year is not None:
        stmt = stmt.where(RegistryObject.case_year == year)
    canonical_stage = _canonical_stage_type(stage_type)
    if canonical_stage:
        stmt = stmt.where(RegistryObject.stage_events.any(StageEvent.stage_type == canonical_stage))
    if only_problematic:
        control_fields = (
            Party.control_decree_without_object,
            Party.control_object_without_decree,
            Party.control_unidentified_rostov_no,
            Party.control_need_recall,
        )
        party_problem = or_(*[
            func.length(func.trim(func.coalesce(field, ""))) > 0
            for field in control_fields
        ])
        object_problem = or_(
            RegistryObject.object_description.ilike("%нет объекта%"),
            RegistryObject.object_description.ilike("%нет биоматериала%"),
            RegistryObject.object_description.ilike("%горел%"),
        )
        stmt = stmt.where(or_(party_problem, object_problem))
    return stmt


@router.get("/registry/preview")
async def export_registry_preview(
    q: str | None = None,
    party_no: str | None = None,
    party_ids: str | None = None,
    object_ids: str | None = None,
    object_nos: str | None = None,
    year: int | None = None,
    stage_type: str | None = None,
    include_archived: bool = False,
    only_problematic: bool = False,
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    stmt = select(
        func.count(distinct(RegistryObject.id)),
        func.count(distinct(RegistryObject.party_id)),
    )
    stmt = _apply_export_filters(
        stmt,
        q=q,
        party_no=party_no,
        party_ids=party_ids,
        object_ids=object_ids,
        object_nos=object_nos,
        year=year,
        stage_type=stage_type,
        include_archived=include_archived,
        only_problematic=only_problematic,
    )
    object_count, party_count = (await session.execute(stmt)).one()
    return {"object_count": int(object_count or 0), "party_count": int(party_count or 0)}


@router.get("/registry.xlsx")
async def export_registry(
    q: str | None = None,
    party_no: str | None = None,
    party_ids: str | None = None,
    object_ids: str | None = None,
    object_nos: str | None = None,
    year: int | None = None,
    stage_type: str | None = None,
    include_archived: bool = False,
    only_problematic: bool = False,
    limit: int = 20000,
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    stmt = (
        select(RegistryObject)
        .options(
            selectinload(RegistryObject.stage_events).selectinload(StageEvent.performers),
            selectinload(RegistryObject.stage_events).selectinload(StageEvent.sample_prep_detail),
            selectinload(RegistryObject.stage_events).selectinload(StageEvent.milling_detail),
            selectinload(RegistryObject.stage_events).selectinload(StageEvent.dna_extraction_detail),
            selectinload(RegistryObject.stage_events).selectinload(StageEvent.realtime_detail),
            selectinload(RegistryObject.stage_events).selectinload(StageEvent.pcr_detail),
            selectinload(RegistryObject.stage_events).selectinload(StageEvent.electrophoresis_detail),
            selectinload(RegistryObject.stage_events).selectinload(StageEvent.analysis_detail),
        )
    )
    stmt = _apply_export_filters(
        stmt,
        q=q,
        party_no=party_no,
        party_ids=party_ids,
        object_ids=object_ids,
        object_nos=object_nos,
        year=year,
        stage_type=stage_type,
        include_archived=include_archived,
        only_problematic=only_problematic,
    ).order_by(RegistryObject.case_year, RegistryObject.party_id, RegistryObject.id).limit(min(max(limit, 1), 20000))
    result = await session.execute(stmt)
    content = build_registry_workbook(list(result.scalars().all()))
    headers = {"Content-Disposition": 'attachment; filename="registry.xlsx"'}
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )
