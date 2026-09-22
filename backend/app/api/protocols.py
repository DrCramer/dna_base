from datetime import date, datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import Integer, String, case, cast, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import admin_user, current_user, db_session, edit_user
from app.models import (
    Employee,
    LabProtocol,
    LabProtocolObject,
    LabProtocolStage,
    LabProtocolStagePerformer,
    ProtocolStageProfile,
    RegistryObject,
    RtResult,
    StageEvent,
    User,
)
from app.protocol_exporters import list_exporters
from app.schemas import (
    ProtocolArchiveOut,
    ProtocolCreateRequest,
    ProtocolDuplicateRequest,
    ProtocolExporterOut,
    ProtocolListOut,
    ProtocolMetaOut,
    ProtocolObjectListOut,
    ProtocolObjectOut,
    ProtocolObjectResolveOut,
    ProtocolOut,
    ProtocolPreviewOut,
    ProtocolPreviewRequest,
    ProtocolProfileCreate,
    ProtocolProfileOut,
    ProtocolProfileUpdate,
    ProtocolRevisionOut,
    ProtocolSummaryOut,
    ProtocolUpdateRequest,
)
from app.services.audit import write_audit
from app.services.protocol_excel import build_protocol_workbook
from app.services.protocol_plate import natural_key
from app.services.protocols import (
    build_protocol_snapshot,
    replace_protocol_relations,
    suggested_protocol_meta,
)


router = APIRouter(prefix="/protocols", tags=["protocols"])


def _csv_ints(value: str | None) -> list[int]:
    if not value:
        return []
    try:
        return sorted({int(item) for item in value.split(",") if item.strip()})
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Некорректный список идентификаторов") from error


def _object_conditions(
    *,
    party_ids: list[int],
    selected_ids: list[int],
    q: str | None,
    object_type: str | None,
    box_no: str | None,
    quick: str | None,
) -> list:
    conditions = [RegistryObject.status != "archived"]
    if party_ids:
        conditions.append(RegistryObject.party_id.in_(party_ids))
    if quick == "selected":
        conditions.append(RegistryObject.id.in_(selected_ids))
    if q:
        needle = f"%{q.strip()}%"
        conditions.append(
            or_(
                RegistryObject.rcsme_reg_no.ilike(needle),
                RegistryObject.decree_no.ilike(needle),
                RegistryObject.external_military_no.ilike(needle),
            )
        )
    if object_type:
        conditions.append(RegistryObject.object_type == object_type)
    if box_no:
        conditions.append(RegistryObject.box_no == box_no)
    if quick == "has_rt":
        conditions.append(exists(select(RtResult.id).where(RtResult.object_id == RegistryObject.id)))
    elif quick == "no_rt":
        conditions.append(~exists(select(RtResult.id).where(RtResult.object_id == RegistryObject.id)))
    elif quick in {"dna_extraction", "realtime", "pcr", "electrophoresis"}:
        conditions.append(
            exists(
                select(StageEvent.id).where(
                    StageEvent.object_id == RegistryObject.id,
                    StageEvent.stage_type == quick,
                    StageEvent.is_cancelled.is_(False),
                )
            )
        )
    return conditions


def _object_order():
    base = func.split_part(func.coalesce(RegistryObject.rcsme_reg_no, ""), "-", 1)
    suffix = func.split_part(func.coalesce(RegistryObject.rcsme_reg_no, ""), "-", 2)
    numeric_base = case((base.op("~")(r"^\d+$"), cast(base, Integer)), else_=None)
    numeric_suffix = case((suffix.op("~")(r"^\d+$"), cast(suffix, Integer)), else_=None)
    return (numeric_base.asc().nullslast(), base.asc(), numeric_suffix.asc().nullslast(), suffix.asc(), RegistryObject.id.asc())


async def _object_rows(
    session: AsyncSession,
    *,
    party_ids: list[int],
    selected_ids: list[int],
    q: str | None,
    object_type: str | None,
    box_no: str | None,
    quick: str | None,
    limit: int,
    offset: int,
) -> tuple[list[ProtocolObjectOut], int]:
    conditions = _object_conditions(
        party_ids=party_ids,
        selected_ids=selected_ids,
        q=q,
        object_type=object_type,
        box_no=box_no,
        quick=quick,
    )
    total = int((await session.execute(select(func.count(RegistryObject.id)).where(*conditions))).scalar_one())
    rows = (
        await session.execute(
            select(RegistryObject)
            .where(*conditions)
            .order_by(*_object_order())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    ids = [item.id for item in rows]
    rt_ids = set(
        (await session.execute(select(RtResult.object_id).where(RtResult.object_id.in_(ids)).distinct())).scalars()
    ) if ids else set()
    stage_rows = (
        await session.execute(
            select(StageEvent.object_id, StageEvent.stage_type)
            .where(StageEvent.object_id.in_(ids), StageEvent.is_cancelled.is_(False))
            .distinct()
        )
    ).all() if ids else []
    stage_map: dict[int, list[str]] = {}
    for object_id, stage_type in stage_rows:
        stage_map.setdefault(object_id, []).append(stage_type)
    items = [
        ProtocolObjectOut(
            id=obj.id,
            party_id=obj.party_id,
            party_no=obj.party_no,
            case_year=obj.case_year,
            rcsme_reg_no=obj.rcsme_reg_no,
            decree_no=obj.decree_no,
            external_military_no=obj.external_military_no,
            object_type=obj.object_type,
            box_no=obj.box_no,
            has_rt=obj.id in rt_ids,
            stage_types=sorted(stage_map.get(obj.id, [])),
        )
        for obj in rows
    ]
    return items, total


def _protocol_out(protocol: LabProtocol, revisions: list[LabProtocol] | None = None) -> ProtocolOut:
    return ProtocolOut(
        id=protocol.id,
        series_key=protocol.series_key,
        protocol_no=protocol.protocol_no,
        protocol_date=protocol.protocol_date,
        name=protocol.name,
        status=protocol.status,
        revision_no=protocol.revision_no,
        comment=protocol.comment,
        created_by_user_id=protocol.created_by_user_id,
        created_at=protocol.created_at,
        updated_at=protocol.updated_at,
        finalized_at=protocol.finalized_at,
        snapshot=protocol.snapshot_json,
        revisions=[
            ProtocolRevisionOut(id=item.id, revision_no=item.revision_no, status=item.status, updated_at=item.updated_at)
            for item in revisions or []
        ],
    )


async def _protocol_or_404(session: AsyncSession, protocol_id: int) -> LabProtocol:
    protocol = await session.get(LabProtocol, protocol_id)
    if not protocol:
        raise HTTPException(status_code=404, detail="Протокол не найден")
    return protocol


@router.get("/meta", response_model=ProtocolMetaOut)
async def protocol_meta(
    protocol_date: date = Query(default_factory=date.today),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    return await suggested_protocol_meta(session, protocol_date)


@router.get("/objects", response_model=ProtocolObjectListOut)
async def list_protocol_objects(
    party_ids: str | None = None,
    selected_ids: str | None = None,
    q: str | None = None,
    object_type: str | None = None,
    box_no: str | None = None,
    quick: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    items, total = await _object_rows(
        session,
        party_ids=_csv_ints(party_ids),
        selected_ids=_csv_ints(selected_ids),
        q=q,
        object_type=object_type,
        box_no=box_no,
        quick=quick,
        limit=limit,
        offset=offset,
    )
    return ProtocolObjectListOut(items=items, total=total, limit=limit, offset=offset)


@router.get("/objects/resolve", response_model=ProtocolObjectResolveOut)
async def resolve_protocol_objects(
    party_ids: str | None = None,
    selected_ids: str | None = None,
    q: str | None = None,
    object_type: str | None = None,
    box_no: str | None = None,
    quick: str | None = None,
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    conditions = _object_conditions(
        party_ids=_csv_ints(party_ids),
        selected_ids=_csv_ints(selected_ids),
        q=q,
        object_type=object_type,
        box_no=box_no,
        quick=quick,
    )
    ids = list(
        (
            await session.execute(
                select(RegistryObject.id).where(*conditions).order_by(*_object_order()).limit(5000)
            )
        ).scalars()
    )
    return ProtocolObjectResolveOut(object_ids=ids, total=len(ids))


@router.get("/profiles", response_model=list[ProtocolProfileOut])
async def list_profiles(
    stage_type: str | None = None,
    include_inactive: bool = False,
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    stmt = select(ProtocolStageProfile)
    if stage_type:
        stmt = stmt.where(ProtocolStageProfile.stage_type == stage_type)
    if not include_inactive:
        stmt = stmt.where(ProtocolStageProfile.active.is_(True))
    return list((await session.execute(stmt.order_by(ProtocolStageProfile.name))).scalars())


@router.post("/profiles", response_model=ProtocolProfileOut)
async def create_profile(
    payload: ProtocolProfileCreate,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(admin_user),
):
    profile = ProtocolStageProfile(**payload.model_dump())
    session.add(profile)
    try:
        await session.flush()
        await write_audit(session, user, "protocol_profile", profile.id, "create", None, {"stage_type": profile.stage_type, "name": profile.name})
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Профиль с таким названием уже существует") from error
    await session.refresh(profile)
    return profile


@router.patch("/profiles/{profile_id}", response_model=ProtocolProfileOut)
async def update_profile(
    profile_id: int,
    payload: ProtocolProfileUpdate,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(admin_user),
):
    profile = await session.get(ProtocolStageProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Профиль не найден")
    before = {"name": profile.name, "active": profile.active}
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, key, value)
    try:
        await write_audit(session, user, "protocol_profile", profile.id, "update", before, {"name": profile.name, "active": profile.active})
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Профиль с таким названием уже существует") from error
    await session.refresh(profile)
    return profile


@router.post("/preview", response_model=ProtocolPreviewOut)
async def preview_protocol(
    payload: ProtocolPreviewRequest,
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(edit_user),
):
    return ProtocolPreviewOut(**await build_protocol_snapshot(session, payload))


@router.get("", response_model=ProtocolListOut)
async def list_protocols(
    q: str | None = None,
    year: int | None = Query(default=None, ge=1900, le=2200),
    status: str | None = None,
    stage_type: str | None = None,
    party_id: int | None = None,
    employee_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    conditions = [LabProtocol.is_current.is_(True)]
    if status:
        conditions.append(LabProtocol.status == status)
    else:
        conditions.append(LabProtocol.status != "archived")
    if year:
        conditions.append(func.extract("year", LabProtocol.protocol_date) == year)
    if date_from:
        conditions.append(LabProtocol.protocol_date >= date_from)
    if date_to:
        conditions.append(LabProtocol.protocol_date <= date_to)
    if stage_type:
        conditions.append(exists(select(LabProtocolStage.id).where(LabProtocolStage.protocol_id == LabProtocol.id, LabProtocolStage.stage_type == stage_type, LabProtocolStage.enabled.is_(True))))
    if party_id:
        conditions.append(exists(select(LabProtocolObject.id).where(LabProtocolObject.protocol_id == LabProtocol.id, LabProtocolObject.party_id == party_id)))
    if employee_id:
        conditions.append(
            exists(
                select(LabProtocolStagePerformer.id)
                .join(
                    LabProtocolStage,
                    LabProtocolStage.id == LabProtocolStagePerformer.protocol_stage_id,
                )
                .where(
                    LabProtocolStage.protocol_id == LabProtocol.id,
                    LabProtocolStagePerformer.employee_id == employee_id,
                )
            )
        )
    if q:
        needle = f"%{q.strip()}%"
        conditions.append(
            or_(
                LabProtocol.name.ilike(needle),
                cast(LabProtocol.protocol_no, String).ilike(needle),
                exists(select(LabProtocolObject.id).where(LabProtocolObject.protocol_id == LabProtocol.id, or_(LabProtocolObject.party_no_snapshot.ilike(needle), LabProtocolObject.rcsme_no_snapshot.ilike(needle), LabProtocolObject.decision_no_snapshot.ilike(needle), LabProtocolObject.military_no_snapshot.ilike(needle)))),
                exists(select(LabProtocolStage.id).where(LabProtocolStage.protocol_id == LabProtocol.id, or_(LabProtocolStage.kit_name_snapshot.ilike(needle), LabProtocolStage.sequencer_name_snapshot.ilike(needle)))),
                exists(
                    select(LabProtocolStagePerformer.id)
                    .join(
                        LabProtocolStage,
                        LabProtocolStage.id == LabProtocolStagePerformer.protocol_stage_id,
                    )
                    .where(
                        LabProtocolStage.protocol_id == LabProtocol.id,
                        LabProtocolStagePerformer.display_name_snapshot.ilike(needle),
                    )
                ),
            )
        )
    total = int((await session.execute(select(func.count(LabProtocol.id)).where(*conditions))).scalar_one())
    protocols = list((await session.execute(select(LabProtocol).where(*conditions).order_by(LabProtocol.protocol_date.desc(), LabProtocol.protocol_no.desc()).limit(limit).offset(offset))).scalars())
    user_ids = {item.created_by_user_id for item in protocols if item.created_by_user_id}
    authors = {item.id: item.username for item in (await session.execute(select(User).where(User.id.in_(user_ids)))).scalars()} if user_ids else {}
    items = []
    for protocol in protocols:
        snapshot = protocol.snapshot_json or {}
        objects = snapshot.get("objects", [])
        items.append(ProtocolSummaryOut(id=protocol.id, series_key=protocol.series_key, protocol_no=protocol.protocol_no, protocol_date=protocol.protocol_date, name=protocol.name, status=protocol.status, revision_no=protocol.revision_no, object_count=len(objects), party_numbers=sorted({str(item.get("party_no")) for item in objects if item.get("party_no")}, key=natural_key), stage_types=[item["stage_type"] for item in snapshot.get("stages", []) if item.get("enabled")], author=authors.get(protocol.created_by_user_id), updated_at=protocol.updated_at))
    return ProtocolListOut(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=ProtocolOut)
async def create_protocol(
    payload: ProtocolCreateRequest,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    preview = await build_protocol_snapshot(session, payload)
    protocol = LabProtocol(series_key=str(uuid4()), protocol_no=payload.protocol_no, protocol_date=payload.protocol_date, name=payload.name.strip(), status="draft", revision_no=1, is_current=True, comment=payload.comment, created_by_user_id=user.id, snapshot_json=preview["snapshot"])
    session.add(protocol)
    try:
        await session.flush()
        await replace_protocol_relations(session, protocol, preview["snapshot"])
        await write_audit(session, user, "lab_protocol", protocol.id, "protocol_created", None, {"protocol_no": protocol.protocol_no, "name": protocol.name, "object_count": preview["selected_count"]})
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Этот номер протокола уже занят на выбранную дату") from error
    await session.refresh(protocol)
    return _protocol_out(protocol, [protocol])


@router.get("/{protocol_id}", response_model=ProtocolOut)
async def get_protocol(
    protocol_id: int,
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    protocol = await _protocol_or_404(session, protocol_id)
    revisions = list((await session.execute(select(LabProtocol).where(LabProtocol.series_key == protocol.series_key).order_by(LabProtocol.revision_no.desc()))).scalars())
    return _protocol_out(protocol, revisions)


@router.patch("/{protocol_id}", response_model=ProtocolOut)
async def update_protocol(
    protocol_id: int,
    payload: ProtocolUpdateRequest,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    protocol = await _protocol_or_404(session, protocol_id)
    if protocol.status != "draft":
        raise HTTPException(status_code=409, detail="Сохранённый протокол нельзя изменить. Создайте новую версию.")
    preview = await build_protocol_snapshot(session, payload)
    protocol.protocol_no = payload.protocol_no
    protocol.protocol_date = payload.protocol_date
    protocol.name = payload.name.strip()
    protocol.comment = payload.comment
    protocol.snapshot_json = preview["snapshot"]
    await replace_protocol_relations(session, protocol, preview["snapshot"])
    await write_audit(session, user, "lab_protocol", protocol.id, "protocol_updated", None, {"revision_no": protocol.revision_no, "object_count": preview["selected_count"]})
    await session.commit()
    await session.refresh(protocol)
    return _protocol_out(protocol)


@router.post("/{protocol_id}/finalize", response_model=ProtocolOut)
async def finalize_protocol(
    protocol_id: int,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    protocol = await _protocol_or_404(session, protocol_id)
    if protocol.status != "draft":
        raise HTTPException(status_code=409, detail="Финализировать можно только черновик")
    protocol.status = "final"
    protocol.finalized_at = datetime.now(timezone.utc)
    await write_audit(session, user, "lab_protocol", protocol.id, "protocol_finalized", {"status": "draft"}, {"status": "final", "revision_no": protocol.revision_no})
    await session.commit()
    await session.refresh(protocol)
    return _protocol_out(protocol)


@router.post("/{protocol_id}/revision", response_model=ProtocolOut)
async def create_revision(
    protocol_id: int,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    source = await _protocol_or_404(session, protocol_id)
    current = (await session.execute(select(LabProtocol).where(LabProtocol.series_key == source.series_key, LabProtocol.is_current.is_(True)))).scalar_one()
    if current.status == "draft":
        return _protocol_out(current)
    current.is_current = False
    revision_no = int((await session.execute(select(func.max(LabProtocol.revision_no)).where(LabProtocol.series_key == source.series_key))).scalar_one()) + 1
    protocol = LabProtocol(series_key=source.series_key, protocol_no=source.protocol_no, protocol_date=source.protocol_date, name=source.name, status="draft", revision_no=revision_no, is_current=True, comment=source.comment, created_by_user_id=user.id, snapshot_json=source.snapshot_json)
    session.add(protocol)
    await session.flush()
    await replace_protocol_relations(session, protocol, source.snapshot_json)
    await write_audit(session, user, "lab_protocol", protocol.id, "protocol_revision_created", None, {"source_id": source.id, "revision_no": revision_no})
    await session.commit()
    await session.refresh(protocol)
    return _protocol_out(protocol)


@router.post("/{protocol_id}/duplicate", response_model=ProtocolOut)
async def duplicate_protocol(
    protocol_id: int,
    payload: ProtocolDuplicateRequest,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    source = await _protocol_or_404(session, protocol_id)
    target_date = payload.protocol_date or date.today()
    meta = await suggested_protocol_meta(session, target_date)
    snapshot = {**source.snapshot_json, "protocol": {**source.snapshot_json.get("protocol", {}), "protocol_date": target_date.isoformat(), "protocol_no": meta["suggested_no"], "name": meta["suggested_name"]}}
    if not payload.copy_objects:
        snapshot = {**snapshot, "objects": [], "dilutions": [], "layouts": {}}
    protocol = LabProtocol(series_key=str(uuid4()), protocol_no=meta["suggested_no"], protocol_date=target_date, name=meta["suggested_name"], status="draft", revision_no=1, is_current=True, comment=source.comment, created_by_user_id=user.id, snapshot_json=snapshot)
    session.add(protocol)
    await session.flush()
    await replace_protocol_relations(session, protocol, snapshot)
    await write_audit(session, user, "lab_protocol", protocol.id, "protocol_duplicated", None, {"source_id": source.id, "copy_objects": payload.copy_objects})
    await session.commit()
    await session.refresh(protocol)
    return _protocol_out(protocol)


@router.post("/{protocol_id}/archive", response_model=ProtocolArchiveOut)
async def archive_protocol(
    protocol_id: int,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(admin_user),
):
    protocol = await _protocol_or_404(session, protocol_id)
    protocol.status = "archived"
    await write_audit(session, user, "lab_protocol", protocol.id, "protocol_archived", None, {"revision_no": protocol.revision_no})
    await session.commit()
    return ProtocolArchiveOut(id=protocol.id, status="archived")


@router.delete("/{protocol_id}", status_code=204)
async def delete_protocol(
    protocol_id: int,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(admin_user),
):
    protocol = await _protocol_or_404(session, protocol_id)
    if protocol.status != "archived":
        raise HTTPException(status_code=409, detail="Сначала архивируйте протокол")
    await write_audit(session, user, "lab_protocol", protocol.id, "protocol_deleted", {"name": protocol.name}, None)
    await session.delete(protocol)
    await session.commit()
    return Response(status_code=204)


@router.get("/{protocol_id}/excel")
async def export_protocol_excel(
    protocol_id: int,
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    protocol = await _protocol_or_404(session, protocol_id)
    content = build_protocol_workbook(protocol.snapshot_json)
    safe_name = "".join(char if char.isalnum() or char in "-_" else "_" for char in protocol.name)
    return Response(content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="protocol_{safe_name}.xlsx"'})


@router.get("/{protocol_id}/exporters", response_model=list[ProtocolExporterOut])
async def protocol_exporters(
    protocol_id: int,
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    await _protocol_or_404(session, protocol_id)
    return [ProtocolExporterOut(key=item.key, stage_type=item.stage_type) for item in list_exporters()]
