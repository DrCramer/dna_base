from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import current_user, db_session, edit_user
from app.models import Party, RegistryObject, StageEvent, User
from app.parsers.normalization import normalize_number, number_base
from app.services.case_year import infer_case_year
from app.schemas import ObjectCreate, ObjectList, ObjectListItemOut, ObjectOut, ObjectUpdate
from app.services.audit import write_audit
from app.services.registry import recalculate_party_counts, search_objects
from app.services.stages import stage_summary_for_objects


router = APIRouter(prefix="/objects", tags=["objects"])


def _object_load_options():
    return (
        selectinload(RegistryObject.prep_events),
        selectinload(RegistryObject.dna_extractions),
        selectinload(RegistryObject.pcr_events),
        selectinload(RegistryObject.electrophoresis_events),
        selectinload(RegistryObject.electrophoresis_analysis_events),
        selectinload(RegistryObject.rt_results),
        selectinload(RegistryObject.electrophoresis_result_files),
        selectinload(RegistryObject.stage_events).selectinload(StageEvent.performers),
        selectinload(RegistryObject.stage_events).selectinload(StageEvent.sample_prep_detail),
        selectinload(RegistryObject.stage_events).selectinload(StageEvent.milling_detail),
        selectinload(RegistryObject.stage_events).selectinload(StageEvent.dna_extraction_detail),
        selectinload(RegistryObject.stage_events).selectinload(StageEvent.realtime_detail),
        selectinload(RegistryObject.stage_events).selectinload(StageEvent.pcr_detail),
        selectinload(RegistryObject.stage_events).selectinload(StageEvent.electrophoresis_detail),
        selectinload(RegistryObject.stage_events).selectinload(StageEvent.analysis_detail),
    )


def _snapshot(obj: RegistryObject) -> dict[str, Any]:
    return {
        "id": obj.id,
        "rcsme_reg_no": obj.rcsme_reg_no,
        "decree_no": obj.decree_no,
        "case_year": obj.case_year,
        "status": obj.status,
        "object_type": obj.object_type,
        "box_no": obj.box_no,
    }


async def _generate_rcsme_reg_no(session: AsyncSession, decree_no: str | None, current_object_id: int, case_year: int | None) -> str | None:
    base = number_base(decree_no)
    if not base:
        return None
    result = await session.execute(
        select(RegistryObject.rcsme_reg_no).where(
            RegistryObject.rcsme_reg_no_base == base,
            RegistryObject.case_year == case_year,
            RegistryObject.id != current_object_id,
        )
    )
    suffixes: list[int] = []
    for value in result.scalars().all():
        normalized = normalize_number(value)
        if not normalized:
            continue
        parts = normalized.split("-", 1)
        if len(parts) != 2 or parts[0] != base:
            continue
        try:
            suffix = int(parts[1])
        except ValueError:
            continue
        if 0 < suffix < 1000:
            suffixes.append(suffix)
    return f"{base}-{(max(suffixes) + 1) if suffixes else 1}"


async def _ensure_unique_number(
    session: AsyncSession,
    object_id: int,
    field: str,
    value: str | None,
    detail: str,
    case_year: int | None = None,
) -> None:
    if not value:
        return
    column = getattr(RegistryObject, field)
    conditions = [column == value, RegistryObject.id != object_id]
    if field == "rcsme_reg_no":
        conditions.append(RegistryObject.case_year == case_year)
    result = await session.execute(select(RegistryObject.id).where(*conditions))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=detail)


@router.get("", response_model=ObjectList)
async def list_objects(
    q: str | None = None,
    party_no: str | None = None,
    status: str | None = None,
    year: int | None = Query(default=None, ge=1900, le=2200),
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    items, total = await search_objects(session, q=q, party_no=party_no, status=status, limit=limit, offset=offset, case_year=year)
    summaries = await stage_summary_for_objects(session, [item.id for item in items])
    payload: list[ObjectListItemOut] = []
    for item in items:
        data = ObjectListItemOut.model_validate(item).model_dump()
        data.update(summaries.get(item.id, {}))
        payload.append(ObjectListItemOut(**data))
    return ObjectList(items=payload, total=total, limit=limit, offset=offset)


@router.get("/{object_id}", response_model=ObjectOut)
async def get_object(
    object_id: int,
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    result = await session.execute(
        select(RegistryObject)
        .where(RegistryObject.id == object_id)
        .options(*_object_load_options())
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Объект не найден")
    return obj


@router.post("", response_model=ObjectOut)
async def create_object(
    payload: ObjectCreate,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    data = payload.model_dump(exclude_unset=True)
    party: Party | None = None
    if data.get("party_id"):
        party = await session.get(Party, data["party_id"])
        if not party:
            raise HTTPException(status_code=404, detail="Партия не найдена")
        data["party_no"] = party.party_no
        data["case_year"] = party.case_year
    elif data.get("party_no"):
        stmt = select(Party).where(Party.party_no == data["party_no"])
        if data.get("case_year"):
            stmt = stmt.where(Party.case_year == data["case_year"])
        result = await session.execute(stmt)
        party = result.scalars().first()
        if party:
            data["party_id"] = party.id
            data["case_year"] = party.case_year

    data["case_year"] = infer_case_year(
        decision_date=data.get("decision_date"),
        decree_no=data.get("decree_no"),
        fallback=data.get("case_year"),
    )
    if "decree_no" in data:
        data["decree_no"] = normalize_number(data["decree_no"])
        data["decree_no_base"] = number_base(data["decree_no"])
        data["case_year"] = infer_case_year(
            decision_date=data.get("decision_date"), decree_no=data.get("decree_no"), fallback=data.get("case_year")
        )
        await _ensure_unique_number(session, 0, "decree_no", data["decree_no"], "№ постановления уже есть в базе")
    if data.get("rcsme_reg_no"):
        data["rcsme_reg_no"] = normalize_number(data["rcsme_reg_no"])
        data["rcsme_reg_no_base"] = number_base(data["rcsme_reg_no"])
        data["rcsme_reg_no_is_manual"] = True
        await _ensure_unique_number(
            session,
            0,
            "rcsme_reg_no",
            data["rcsme_reg_no"],
            "№ рег РЦСМЭ уже есть в базе",
            data.get("case_year"),
        )
    else:
        generated = await _generate_rcsme_reg_no(session, data.get("decree_no"), 0, data.get("case_year"))
        if generated:
            data["rcsme_reg_no"] = generated
            data["rcsme_reg_no_base"] = number_base(generated)
            data["rcsme_reg_no_is_manual"] = False
    if not _compact_text(data.get("object_description")):
        data["object_description"] = "кость"
    status = data.pop("status", None) or "new"
    obj = RegistryObject(**data, status=status, raw_registry_json={})
    session.add(obj)
    await session.flush()
    if party:
        await recalculate_party_counts(session, {party.id})
    await write_audit(session, user, "object", obj.id, "create", None, _snapshot(obj))
    await session.commit()
    result = await session.execute(select(RegistryObject).where(RegistryObject.id == obj.id).options(*_object_load_options()))
    return result.scalar_one()


@router.patch("/{object_id}", response_model=ObjectOut)
async def update_object(
    object_id: int,
    payload: ObjectUpdate,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    obj = await session.get(RegistryObject, object_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Объект не найден")
    before = _snapshot(obj)
    old_party_id = obj.party_id
    data = payload.model_dump(exclude_unset=True)
    if data.get("party_id"):
        party = await session.get(Party, data["party_id"])
        if not party:
            raise HTTPException(status_code=404, detail="Партия не найдена")
        data["party_no"] = party.party_no
        data["case_year"] = party.case_year
    elif data.get("party_no"):
        stmt = select(Party).where(Party.party_no == data["party_no"])
        if data.get("case_year"):
            stmt = stmt.where(Party.case_year == data["case_year"])
        result = await session.execute(stmt)
        party = result.scalars().first()
        if party:
            data["party_id"] = party.id
            data["case_year"] = party.case_year
    if "decision_date" in data and "decree_no" not in data and "rcsme_reg_no" not in data:
        data["case_year"] = infer_case_year(
            decision_date=data.get("decision_date"),
            decree_no=obj.decree_no,
            fallback=data.get("case_year", obj.case_year),
        )
        await _ensure_unique_number(
            session,
            obj.id,
            "rcsme_reg_no",
            obj.rcsme_reg_no,
            "№ рег РЦСМЭ уже есть в базе за выбранный год",
            data.get("case_year"),
        )

    if "decree_no" in data:
        data["decree_no"] = normalize_number(data["decree_no"])
        data["decree_no_base"] = number_base(data["decree_no"])
        data["case_year"] = infer_case_year(decision_date=data.get("decision_date", obj.decision_date), decree_no=data.get("decree_no"), fallback=data.get("case_year", obj.case_year))
        await _ensure_unique_number(session, obj.id, "decree_no", data["decree_no"], "№ постановления уже есть в базе")
        if "rcsme_reg_no" not in data and not obj.rcsme_reg_no_is_manual:
            generated = await _generate_rcsme_reg_no(session, data["decree_no"], obj.id, data.get("case_year"))
            if generated:
                data["rcsme_reg_no"] = generated
                data["rcsme_reg_no_base"] = number_base(generated)
                data["rcsme_reg_no_is_manual"] = False
    if "rcsme_reg_no" in data:
        data["rcsme_reg_no"] = normalize_number(data["rcsme_reg_no"])
        data["rcsme_reg_no_base"] = number_base(data["rcsme_reg_no"])
        data["rcsme_reg_no_is_manual"] = True
        data["case_year"] = infer_case_year(decision_date=data.get("decision_date", obj.decision_date), decree_no=data.get("decree_no", obj.decree_no), fallback=data.get("case_year", obj.case_year))
        await _ensure_unique_number(session, obj.id, "rcsme_reg_no", data["rcsme_reg_no"], "№ рег РЦСМЭ уже есть в базе", data.get("case_year"))
    for key, value in data.items():
        setattr(obj, key, value)
    await write_audit(session, user, "object", obj.id, "update", before, _snapshot(obj))
    affected_party_ids = {party_id for party_id in (old_party_id, obj.party_id) if party_id}
    if affected_party_ids:
        await recalculate_party_counts(session, affected_party_ids)
    await session.commit()
    result = await session.execute(
        select(RegistryObject).where(RegistryObject.id == object_id).options(*_object_load_options())
    )
    return result.scalar_one()


@router.post("/{object_id}/archive", response_model=ObjectOut)
async def archive_object(
    object_id: int,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    obj = await session.get(RegistryObject, object_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Объект не найден")
    before = _snapshot(obj)
    affected_party_ids = {obj.party_id} if obj.party_id else set()
    archived_ids = [obj.id]
    obj.status = "archived"

    if not obj.parent_object_id:
        repeats = (
            await session.execute(
                select(RegistryObject).where(
                    RegistryObject.parent_object_id == obj.id,
                    RegistryObject.party_id == obj.party_id,
                    RegistryObject.status != "archived",
                )
            )
        ).scalars().all()
        for repeat in repeats:
            repeat.status = "archived"
            archived_ids.append(repeat.id)

    await write_audit(
        session,
        user,
        "object",
        obj.id,
        "archive",
        before,
        {"archived_object_ids": archived_ids, **_snapshot(obj)},
    )
    if affected_party_ids:
        await recalculate_party_counts(session, affected_party_ids)
    await session.commit()
    result = await session.execute(
        select(RegistryObject).where(RegistryObject.id == object_id).options(*_object_load_options())
    )
    return result.scalar_one()
