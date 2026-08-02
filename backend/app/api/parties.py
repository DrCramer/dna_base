from datetime import date
from typing import Any
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Integer, and_, case, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import admin_user, current_user, db_session, edit_user
from app.models import ElectrophoresisResultFile, Party, RegistryObject, RtResult, StageEvent, User, WorkSession
from app.parsers.normalization import normalize_number, number_base
from app.services.case_year import infer_case_year, normalize_case_year
from app.services.no_object import control_no_tokens
from app.schemas import (
    ObjectList,
    ObjectListItemOut,
    PartyCreate,
    PartyList,
    PartyOut,
    PartyYearsOut,
    PartyPermanentDeleteOut,
    PartyProgressOut,
    PartyUpdate,
    RegistrationBulkApplyOut,
    RegistrationBulkPreviewOut,
    RegistrationBulkRequest,
    RegistrationBulkRow,
)
from app.services.audit import write_audit
from app.services.registry import recalculate_party_counts
from app.services.stages import stage_summary_for_objects


router = APIRouter(prefix="/parties", tags=["parties"])


def _party_snapshot(party: Party) -> dict[str, Any]:
    return {
        "id": party.id,
        "party_no": party.party_no,
        "title": party.title,
        "status": party.status,
        "object_count": party.object_count,
    }


def _validate_control_lists(payload_data: dict[str, Any], party: Party) -> None:
    no_object = payload_data.get("control_decree_without_object", party.control_decree_without_object)
    no_decree = payload_data.get("control_object_without_decree", party.control_object_without_decree)
    overlap = sorted(control_no_tokens(no_object) & control_no_tokens(no_decree))
    if overlap:
        shown = ", ".join(overlap[:5])
        suffix = "..." if len(overlap) > 5 else ""
        raise HTTPException(
            status_code=400,
            detail=f"Один номер не может быть одновременно в «Нет объекта» и «Нет постановления»: {shown}{suffix}",
        )


def _object_snapshot(obj: RegistryObject) -> dict[str, Any]:
    return {
        "id": obj.id,
        "party_id": obj.party_id,
        "party_no": obj.party_no,
        "registry_row_no": obj.registry_row_no,
        "rcsme_reg_no": obj.rcsme_reg_no,
        "decree_no": obj.decree_no,
        "external_military_no": obj.external_military_no,
        "intake_date": obj.intake_date.isoformat() if obj.intake_date else None,
        "decision_date": obj.decision_date.isoformat() if obj.decision_date else None,
        "investigator": obj.investigator,
        "incoming_no": obj.incoming_no,
        "box_no": obj.box_no,
        "status": obj.status,
    }


async def _party_or_404(session: AsyncSession, party_id: int) -> Party:
    party = await session.get(Party, party_id)
    if not party:
        raise HTTPException(status_code=404, detail="Партия не найдена")
    return party


def _party_out(party: Party, object_count: int | None = None) -> PartyOut:
    data = PartyOut.model_validate(party).model_dump()
    if object_count is not None:
        data["object_count"] = object_count
    return PartyOut(**data)


def _parse_rcsme_start(value: str) -> tuple[int, int]:
    normalized = normalize_number(value)
    if not normalized:
        raise HTTPException(status_code=400, detail="Укажите начальный № рег РЦСМЭ")
    if "-" in normalized:
        base_text, suffix_text = normalized.split("-", 1)
    else:
        base_text, suffix_text = normalized, "1"
    if not base_text.isdigit() or not suffix_text.isdigit():
        raise HTTPException(status_code=400, detail="Начальный № рег РЦСМЭ должен быть в формате 100-1")
    return int(base_text), int(suffix_text)


async def _global_registration_start_hint(session: AsyncSession, case_year: int) -> tuple[str, str | None, str | None]:
    row = (
        await session.execute(
            select(RegistryObject.rcsme_reg_no, RegistryObject.rcsme_reg_no_base, Party.party_no)
            .join(Party, Party.id == RegistryObject.party_id)
            .where(
                RegistryObject.status != "archived",
                RegistryObject.case_year == case_year,
                RegistryObject.rcsme_reg_no_base.op("~")(r"^\d+$"),
            )
            .order_by(RegistryObject.rcsme_reg_no_base.cast(Integer).desc(), RegistryObject.id.desc())
            .limit(1)
        )
    ).first()
    if not row:
        return "1-1", None, None
    rcsme_reg_no, rcsme_reg_no_base, party_no = row
    max_base = int(rcsme_reg_no_base)
    return f"{max_base + 1}-1", party_no, rcsme_reg_no or f"{max_base}-1"


def _compact_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _overlay_text(current: str | None, incoming: str | None) -> str | None:
    value = _compact_text(incoming)
    return value if value is not None else current


async def _registration_party_objects(session: AsyncSession, party_id: int, limit: int) -> list[RegistryObject]:
    result = await session.execute(
        select(RegistryObject)
        .where(RegistryObject.party_id == party_id, RegistryObject.status != "archived")
        .order_by(
            func.nullif(RegistryObject.rcsme_reg_no_base, "").cast(Integer).nullslast(),
            RegistryObject.parent_object_id.asc().nullsfirst(),
            RegistryObject.repeat_suffix.asc().nullsfirst(),
            RegistryObject.rcsme_reg_no.asc().nullslast(),
            RegistryObject.id.asc(),
        )
        .limit(limit)
    )
    return list(result.scalars().all())


async def _registration_bulk_preview(
    session: AsyncSession,
    party: Party,
    payload: RegistrationBulkRequest,
) -> RegistrationBulkPreviewOut:
    if payload.count < 1 or payload.count > 500:
        raise HTTPException(status_code=400, detail="Количество объектов должно быть от 1 до 500")
    requested_year = infer_case_year(decision_date=payload.decision_date, fallback=party.case_year) or date.today().year
    suggested_start, previous_party_no, previous_last = await _global_registration_start_hint(session, requested_year)
    existing_count = int(
        (
            await session.execute(
                select(func.count(RegistryObject.id)).where(
                    RegistryObject.party_id == party.id,
                    RegistryObject.status != "archived",
                )
            )
        ).scalar_one()
    )
    start_base, suffix = _parse_rcsme_start(payload.start_rcsme_reg_no or suggested_start)
    year = requested_year
    external_numbers = [_compact_text(item) for item in payload.external_military_numbers]
    external_numbers = [item for item in external_numbers if item]
    if payload.update_existing:
        objects = await _registration_party_objects(session, party.id, payload.count)
        extra_external = external_numbers[len(objects):]
        rows = [
            RegistrationBulkRow(
                index=index + 1,
                object_id=obj.id,
                registry_row_no=obj.registry_row_no or str(index + 1),
                rcsme_reg_no=obj.rcsme_reg_no,
                decree_no=obj.decree_no or "",
                external_military_no=external_numbers[index] if index < len(external_numbers) else obj.external_military_no,
                intake_date=payload.intake_date or obj.intake_date,
                decision_date=payload.decision_date or obj.decision_date,
                investigator=_overlay_text(obj.investigator, payload.investigator),
                incoming_no=_overlay_text(obj.incoming_no, payload.incoming_no),
                box_no=_overlay_text(obj.box_no, payload.box_no),
                conflicts=[],
            )
            for index, obj in enumerate(objects)
        ]
        warnings: list[str] = []
        if not objects:
            warnings.append("В партии нет активных объектов для обновления.")
        elif existing_count > len(objects):
            warnings.append(f"Будут обновлены первые {len(objects)} из {existing_count} объект(ов) партии.")
        else:
            warnings.append(f"Будут обновлены существующие объекты партии: {len(objects)}.")
        if extra_external:
            warnings.append(f"В списке № в в/ч №522 есть лишние значения: {len(extra_external)}.")
        return RegistrationBulkPreviewOut(
            suggested_start_rcsme_reg_no=suggested_start,
            previous_party_no=previous_party_no,
            previous_last_rcsme_reg_no=previous_last,
            case_year=year,
            existing_party_object_count=existing_count,
            rows=rows,
            conflicts=[],
            warnings=warnings,
            extra_external_military_numbers=extra_external,
        )

    extra_external = external_numbers[payload.count:]
    rows: list[RegistrationBulkRow] = []
    rcsme_numbers = [f"{start_base + index}-{suffix}" for index in range(payload.count)]
    decree_numbers = [f"{start_base + index}-{year}" for index in range(payload.count)]
    existing_rows = await session.execute(
        select(RegistryObject.rcsme_reg_no, RegistryObject.decree_no).where(
            or_(
                RegistryObject.decree_no.in_(decree_numbers),
                and_(RegistryObject.case_year == year, RegistryObject.rcsme_reg_no.in_(rcsme_numbers)),
            )
        )
    )
    existing_rcsme = set()
    existing_decree = set()
    for rcsme_reg_no, decree_no in existing_rows.all():
        if rcsme_reg_no:
            existing_rcsme.add(rcsme_reg_no)
        if decree_no:
            existing_decree.add(decree_no)
    conflicts: list[str] = []
    for index in range(payload.count):
        base = start_base + index
        rcsme_reg_no = f"{base}-{suffix}"
        decree_no = f"{base}-{year}"
        row_conflicts: list[str] = []
        if rcsme_reg_no in existing_rcsme:
            row_conflicts.append("№ рег РЦСМЭ уже есть")
        if decree_no in existing_decree:
            row_conflicts.append("№ постановления уже есть")
        if row_conflicts:
            conflicts.append(f"{rcsme_reg_no}: {', '.join(row_conflicts)}")
        rows.append(
            RegistrationBulkRow(
                index=index + 1,
                registry_row_no=str(existing_count + index + 1),
                rcsme_reg_no=rcsme_reg_no,
                decree_no=decree_no,
                external_military_no=external_numbers[index] if index < len(external_numbers) else None,
                intake_date=payload.intake_date,
                decision_date=payload.decision_date,
                investigator=_compact_text(payload.investigator),
                incoming_no=_compact_text(payload.incoming_no),
                box_no=_compact_text(payload.box_no),
                conflicts=row_conflicts,
            )
        )
    warnings: list[str] = []
    if existing_count:
        warnings.append(f"В партии уже есть {existing_count} объект(ов); новые строки будут добавлены после них.")
    if len(external_numbers) < payload.count:
        warnings.append("Список № в в/ч №522 короче количества объектов; часть строк будет без этого номера.")
    if extra_external:
        warnings.append(f"В списке № в в/ч №522 есть лишние значения: {len(extra_external)}.")
    return RegistrationBulkPreviewOut(
        suggested_start_rcsme_reg_no=suggested_start,
        previous_party_no=previous_party_no,
        previous_last_rcsme_reg_no=previous_last,
        case_year=year,
        existing_party_object_count=existing_count,
        rows=rows,
        conflicts=conflicts,
        warnings=warnings,
        extra_external_military_numbers=extra_external,
    )


async def _actual_party_counts(session: AsyncSession, party_ids: list[int]) -> dict[int, int]:
    if not party_ids:
        return {}
    rows = await session.execute(
        select(RegistryObject.party_id, func.count(RegistryObject.id))
        .where(RegistryObject.party_id.in_(party_ids), RegistryObject.status != "archived")
        .group_by(RegistryObject.party_id)
    )
    return {party_id: int(count) for party_id, count in rows.all()}


async def _object_list_response(
    session: AsyncSession,
    items: list[RegistryObject],
    total: int,
    limit: int | None,
    offset: int,
) -> ObjectList:
    summaries = await stage_summary_for_objects(session, [item.id for item in items])
    payload: list[ObjectListItemOut] = []
    for item in items:
        data = ObjectListItemOut.model_validate(item).model_dump()
        data.update(summaries.get(item.id, {}))
        payload.append(ObjectListItemOut(**data))
    return ObjectList(items=payload, total=total, limit=limit, offset=offset)


@router.get("", response_model=PartyList)
async def list_parties(
    q: str | None = None,
    status: str | None = None,
    include_archived: bool = False,
    year: int | None = Query(default=None, ge=1900, le=2200),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    stmt = select(Party)
    count_stmt = select(func.count(Party.id))
    conditions = []
    if q:
        needle = f"%{q.strip()}%"
        conditions.append(or_(Party.party_no.ilike(needle), Party.title.ilike(needle), Party.comment.ilike(needle)))
    if year is not None:
        conditions.append(Party.case_year == year)
    if status:
        conditions.append(Party.status == status)
    elif not include_archived:
        conditions.append(Party.status != "archived")
    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
    total = int((await session.execute(count_stmt)).scalar_one())
    numeric_party_no = case(
        (Party.party_no.op("~")(r"^\d+$"), Party.party_no.cast(Integer)),
        else_=None,
    )
    result = await session.execute(
        stmt.order_by(
            numeric_party_no.desc().nullslast(),
            Party.party_no.desc(),
            Party.id.desc(),
        ).limit(limit).offset(offset)
    )
    parties = list(result.scalars().all())
    counts = await _actual_party_counts(session, [party.id for party in parties])
    return PartyList(items=[_party_out(party, counts.get(party.id, 0)) for party in parties], total=total)


@router.get("/years", response_model=PartyYearsOut)
async def list_party_years(
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    rows = (await session.execute(select(Party.case_year).where(Party.case_year.is_not(None)).distinct())).scalars().all()
    current = date.today().year
    years = {int(year) for year in rows if year}
    ordered = sorted(years, reverse=True)
    return PartyYearsOut(years=ordered, default_year=ordered[0] if ordered else current)


@router.post("", response_model=PartyOut)
async def create_party(
    payload: PartyCreate,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    party = Party(
        party_no=payload.party_no.strip(),
        case_year=normalize_case_year(payload.case_year) or date.today().year,
        title=payload.title or payload.party_no.strip(),
        comment=payload.comment,
        status=payload.status,
        created_by_user_id=user.id,
        object_count=0,
        raw_control_json={},
    )
    session.add(party)
    await session.flush()
    await write_audit(session, user, "party", party.id, "create", None, _party_snapshot(party))
    await session.commit()
    await session.refresh(party)
    return _party_out(party, 0)


@router.get("/{party_id}", response_model=PartyOut)
async def get_party(
    party_id: int,
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    party = await _party_or_404(session, party_id)
    counts = await _actual_party_counts(session, [party.id])
    return _party_out(party, counts.get(party.id, 0))


@router.patch("/{party_id}", response_model=PartyOut)
async def update_party(
    party_id: int,
    payload: PartyUpdate,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    party = await _party_or_404(session, party_id)
    before = _party_snapshot(party)
    payload_data = payload.model_dump(exclude_unset=True)
    _validate_control_lists(payload_data, party)
    for key, value in payload_data.items():
        setattr(party, key, value)
    await write_audit(session, user, "party", party.id, "update", before, _party_snapshot(party))
    await session.commit()
    await session.refresh(party)
    counts = await _actual_party_counts(session, [party.id])
    return _party_out(party, counts.get(party.id, 0))


@router.post("/{party_id}/registration-bulk/preview", response_model=RegistrationBulkPreviewOut)
async def preview_registration_bulk(
    party_id: int,
    payload: RegistrationBulkRequest,
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(edit_user),
):
    party = await _party_or_404(session, party_id)
    return await _registration_bulk_preview(session, party, payload)


@router.post("/{party_id}/registration-bulk/apply", response_model=RegistrationBulkApplyOut)
async def apply_registration_bulk(
    party_id: int,
    payload: RegistrationBulkRequest,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    party = await _party_or_404(session, party_id)
    preview = await _registration_bulk_preview(session, party, payload)
    if preview.conflicts:
        raise HTTPException(status_code=409, detail="Есть конфликты номеров: " + "; ".join(preview.conflicts[:8]))
    if payload.update_existing:
        updated = 0
        for row in preview.rows:
            if not row.object_id:
                continue
            obj = await session.get(RegistryObject, row.object_id)
            if not obj or obj.party_id != party.id or obj.status == "archived":
                continue
            before = _object_snapshot(obj)
            obj.registry_row_no = row.registry_row_no
            obj.intake_date = row.intake_date
            obj.decision_date = row.decision_date
            obj.investigator = row.investigator
            obj.incoming_no = row.incoming_no
            obj.external_military_no = row.external_military_no
            obj.box_no = row.box_no
            if obj.decree_no:
                obj.decree_no_base = number_base(obj.decree_no)
            if obj.rcsme_reg_no:
                obj.rcsme_reg_no_base = number_base(obj.rcsme_reg_no)
            after = _object_snapshot(obj)
            if before != after:
                updated += 1
                await write_audit(session, user, "object", obj.id, "registration_bulk_update", before, after)
        await recalculate_party_counts(session, {party.id})
        await write_audit(
            session,
            user,
            "party",
            party.id,
            "registration_bulk_update",
            None,
            {"objects_updated": updated},
        )
        await session.commit()
        return RegistrationBulkApplyOut(
            party_id=party.id,
            party_no=party.party_no,
            objects_created=0,
            objects_updated=updated,
            rows=preview.rows,
            warnings=preview.warnings,
        )

    created = 0
    for row in preview.rows:
        obj = RegistryObject(
            party_id=party.id,
            party_no=party.party_no,
            case_year=preview.case_year,
            registry_row_no=row.registry_row_no,
            intake_date=row.intake_date,
            decision_date=row.decision_date,
            investigator=row.investigator,
            incoming_no=row.incoming_no,
            decree_no=row.decree_no,
            decree_no_base=number_base(row.decree_no),
            external_military_no=row.external_military_no,
            box_no=row.box_no,
            object_description="кость",
            rcsme_reg_no=row.rcsme_reg_no,
            rcsme_reg_no_base=number_base(row.rcsme_reg_no),
            rcsme_reg_no_is_manual=True,
            status="new",
            raw_registry_json={"source": "registration_bulk"},
        )
        session.add(obj)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(status_code=409, detail=f"Конфликт номера при создании {row.rcsme_reg_no}") from None
        created += 1
        await write_audit(session, user, "object", obj.id, "registration_bulk_create", None, _object_snapshot(obj))
    await recalculate_party_counts(session, {party.id})
    await write_audit(
        session,
        user,
        "party",
        party.id,
        "registration_bulk",
        None,
        {"objects_created": created, "start_rcsme_reg_no": preview.rows[0].rcsme_reg_no if preview.rows else None},
    )
    await session.commit()
    return RegistrationBulkApplyOut(
        party_id=party.id,
        party_no=party.party_no,
        objects_created=created,
        objects_updated=0,
        rows=preview.rows,
        warnings=preview.warnings,
    )


@router.delete("/{party_id}", response_model=PartyPermanentDeleteOut)
async def delete_archived_party_permanently(
    party_id: int,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(admin_user),
):
    party = await _party_or_404(session, party_id)
    if party.status != "archived":
        raise HTTPException(status_code=400, detail="Сначала переместите партию в архив")

    object_ids = list(
        (
            await session.execute(select(RegistryObject.id).where(RegistryObject.party_id == party.id))
        ).scalars().all()
    )
    objects_deleted = len(object_ids)
    stage_events_deleted = 0
    rt_results_deleted = 0
    files_deleted = 0
    file_paths: list[str] = []

    if object_ids:
        stage_events_deleted = int(
            (
                await session.execute(
                    select(func.count(StageEvent.id)).where(StageEvent.object_id.in_(object_ids))
                )
            ).scalar_one()
        )
        rt_results_deleted = int(
            (
                await session.execute(select(func.count(RtResult.id)).where(RtResult.object_id.in_(object_ids)))
            ).scalar_one()
        )
        file_rows = (
            await session.execute(
                select(ElectrophoresisResultFile.file_path).where(ElectrophoresisResultFile.object_id.in_(object_ids))
            )
        ).scalars().all()
        for path in file_rows:
            if not path:
                continue
            try:
                file_path = Path(path)
                if file_path.exists() and file_path.is_file():
                    file_path.unlink()
                    files_deleted += 1
            except OSError:
                file_paths.append(path)
        await session.execute(delete(RtResult).where(RtResult.object_id.in_(object_ids)))

    work_sessions_deleted = int(
        (
            await session.execute(select(func.count(WorkSession.id)).where(WorkSession.party_id == party.id))
        ).scalar_one()
    )

    before = {
        **_party_snapshot(party),
        "objects_deleted": objects_deleted,
        "stage_events_deleted": stage_events_deleted,
        "rt_results_deleted": rt_results_deleted,
        "files_deleted": files_deleted,
        "files_not_deleted": file_paths,
        "work_sessions_deleted": work_sessions_deleted,
    }
    await write_audit(session, user, "party", party.id, "delete_permanent", before, None)
    if object_ids:
        await session.execute(delete(RegistryObject).where(RegistryObject.id.in_(object_ids)))
    await session.execute(delete(WorkSession).where(WorkSession.party_id == party.id))
    await session.delete(party)
    await session.commit()
    return PartyPermanentDeleteOut(
        party_id=party_id,
        party_no=before["party_no"],
        objects_deleted=objects_deleted,
        stage_events_deleted=stage_events_deleted,
        rt_results_deleted=rt_results_deleted,
        files_deleted=files_deleted,
    )


@router.get("/{party_id}/objects", response_model=ObjectList)
async def party_objects(
    party_id: int,
    q: str | None = None,
    status: str | None = None,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    await _party_or_404(session, party_id)
    stmt = select(RegistryObject).where(RegistryObject.party_id == party_id)
    count_stmt = select(func.count(RegistryObject.id)).where(RegistryObject.party_id == party_id)
    if q:
        needle = f"%{q.strip()}%"
        condition = or_(
            RegistryObject.rcsme_reg_no.ilike(needle),
            RegistryObject.decree_no.ilike(needle),
            RegistryObject.external_military_no.ilike(needle),
            RegistryObject.object_description.ilike(needle),
            RegistryObject.object_type.ilike(needle),
            RegistryObject.investigator.ilike(needle),
        )
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
    if status:
        stmt = stmt.where(RegistryObject.status == status)
        count_stmt = count_stmt.where(RegistryObject.status == status)
    else:
        stmt = stmt.where(RegistryObject.status != "archived")
        count_stmt = count_stmt.where(RegistryObject.status != "archived")
    total = int((await session.execute(count_stmt)).scalar_one())
    stmt = stmt.order_by(
        func.nullif(RegistryObject.rcsme_reg_no_base, "").cast(Integer).nullslast(),
        RegistryObject.parent_object_id.asc().nullsfirst(),
        RegistryObject.repeat_suffix.asc().nullsfirst(),
        RegistryObject.rcsme_reg_no.asc().nullslast(),
        RegistryObject.id.asc(),
    ).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return await _object_list_response(session, list(result.scalars().all()), total, limit, offset)


@router.get("/{party_id}/progress", response_model=PartyProgressOut)
async def party_progress(
    party_id: int,
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    await _party_or_404(session, party_id)
    object_count = int(
        (
            await session.execute(
                select(func.count(RegistryObject.id)).where(
                    RegistryObject.party_id == party_id,
                    RegistryObject.status != "archived",
                )
            )
        ).scalar_one()
    )
    stage_result = await session.execute(
        select(StageEvent.stage_type, func.count(StageEvent.id))
        .join(RegistryObject, RegistryObject.id == StageEvent.object_id)
        .where(
            RegistryObject.party_id == party_id,
            RegistryObject.status != "archived",
            StageEvent.is_cancelled.is_(False),
        )
        .group_by(StageEvent.stage_type)
    )
    stage_counts = {stage_type: int(count) for stage_type, count in stage_result.all()}
    completed_objects = int(
        (
            await session.execute(
                select(func.count(func.distinct(StageEvent.object_id)))
                .join(RegistryObject, RegistryObject.id == StageEvent.object_id)
                .where(
                    RegistryObject.party_id == party_id,
                    RegistryObject.status != "archived",
                    StageEvent.is_cancelled.is_(False),
                )
            )
        ).scalar_one()
    )
    return PartyProgressOut(
        party_id=party_id,
        object_count=object_count,
        stage_counts=stage_counts,
        completed_objects=completed_objects,
        objects_without_events=max(object_count - completed_objects, 0),
    )
