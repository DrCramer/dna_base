from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import current_user, db_session, edit_user
from app.models import RegistryObject, StageEvent, User, WorkSession, WorkSessionObject
from app.schemas import (
    ObjectListItemOut,
    WorkSessionCommitRequest,
    WorkSessionCommitResponse,
    WorkSessionOut,
    WorkSessionPreviewRequest,
    WorkSessionPreviewResponse,
)
from app.services.audit import write_audit
from app.services.no_object import object_is_no_object, party_no_object_controls
from app.services.stages import create_stage_event


router = APIRouter(prefix="/work-sessions", tags=["work-sessions"])


STAGE_DATE_FIELDS = {
    "sample_prep": ("washing_date", "bone_tissue_date"),
    "milling": ("milling_date",),
    "dna_extraction": ("extraction_date",),
    "realtime": ("quant_date",),
    "pcr": ("pcr_date",),
    "electrophoresis": ("electrophoresis_date",),
    "analysis": ("analysis_date",),
}


def _event_date(stage_type: str, work_date: date | None, detail_data: dict[str, Any]) -> date | None:
    if work_date:
        return work_date
    for field in STAGE_DATE_FIELDS.get(stage_type, ()):
        value = detail_data.get(field)
        if isinstance(value, date):
            return value
        if isinstance(value, str) and value:
            try:
                return date.fromisoformat(value)
            except ValueError:
                continue
    return None


async def _selected_objects(session: AsyncSession, payload: WorkSessionPreviewRequest) -> list[RegistryObject]:
    conditions = []
    if payload.object_ids:
        conditions.append(RegistryObject.id.in_(payload.object_ids))
    if payload.party_ids:
        conditions.append(RegistryObject.party_id.in_(payload.party_ids))
    if not conditions:
        return []
    stmt = select(RegistryObject).options(selectinload(RegistryObject.parent_object)).where(or_(*conditions)).order_by(RegistryObject.id)
    result = await session.execute(stmt)
    objects: dict[int, RegistryObject] = {}
    for obj in result.scalars().all():
        objects[obj.id] = obj
    return list(objects.values())


async def _editable_stage_objects(session: AsyncSession, objects: list[RegistryObject], stage_type: str) -> tuple[list[RegistryObject], int]:
    if stage_type in ("registration", "all") or not objects:
        return objects, 0
    party_ids = sorted({obj.party_id for obj in objects if obj.party_id})
    controls = await party_no_object_controls(session, party_ids)
    editable: list[RegistryObject] = []
    blocked = 0
    for obj in objects:
        if object_is_no_object(obj, controls.get(obj.party_id or 0, set())):
            blocked += 1
        else:
            editable.append(obj)
    return editable, blocked


async def _existing_stage_counts(
    session: AsyncSession, objects: list[RegistryObject], stage_type: str
) -> dict[int, int]:
    if not objects:
        return {}
    result = await session.execute(
        select(StageEvent.object_id, func.count(StageEvent.id))
        .where(
            StageEvent.object_id.in_([obj.id for obj in objects]),
            StageEvent.stage_type == stage_type,
            StageEvent.is_cancelled.is_(False),
        )
        .group_by(StageEvent.object_id)
    )
    return {object_id: int(count) for object_id, count in result.all()}


@router.post("/preview", response_model=WorkSessionPreviewResponse)
async def preview_work_session(
    payload: WorkSessionPreviewRequest,
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(edit_user),
):
    selected_objects = await _selected_objects(session, payload)
    objects, blocked_count = await _editable_stage_objects(session, selected_objects, payload.stage_type)
    existing_counts = await _existing_stage_counts(session, objects, payload.stage_type)
    next_attempts = [existing_counts.get(obj.id, 0) + 1 for obj in objects] or [1]
    response = WorkSessionPreviewResponse(
        object_count=len(objects),
        party_ids=payload.party_ids,
        stage_type=payload.stage_type,
        objects_with_existing_stage=sum(1 for obj in objects if existing_counts.get(obj.id, 0) > 0),
        objects_without_stage=sum(1 for obj in objects if existing_counts.get(obj.id, 0) == 0),
        next_attempt_min=min(next_attempts),
        next_attempt_max=max(next_attempts),
        sample_objects=[ObjectListItemOut.model_validate(obj) for obj in objects[:20]],
    )
    if blocked_count:
        response.warnings.append(f"Пропущено объектов с отметкой «Нет объекта»: {blocked_count}.")
    return response


@router.post("/commit", response_model=WorkSessionCommitResponse)
async def commit_work_session(
    payload: WorkSessionCommitRequest,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    selected_objects = await _selected_objects(session, payload)
    objects, blocked_count = await _editable_stage_objects(session, selected_objects, payload.stage_type)
    if not objects:
        if blocked_count:
            raise HTTPException(status_code=400, detail="Все выбранные объекты помечены как «Нет объекта»")
        raise HTTPException(status_code=400, detail="Не выбраны объекты для сессии")
    party_id = payload.party_ids[0] if len(payload.party_ids) == 1 else None
    work_session = WorkSession(
        party_id=party_id,
        stage_type=payload.stage_type,
        title=payload.title,
        work_date=payload.work_date,
        comment=payload.comment,
        created_by_user_id=user.id,
        source=payload.source,
        status="applied",
        raw_json={**payload.model_dump(mode="json"), "blocked_no_object_count": blocked_count},
    )
    session.add(work_session)
    await session.flush()

    event_date = _event_date(payload.stage_type, payload.work_date, payload.detail_data)
    created = 0
    for index, obj in enumerate(objects):
        session.add(
            WorkSessionObject(
                work_session_id=work_session.id,
                object_id=obj.id,
                object_order=index,
                is_excluded=False,
            )
        )
        await create_stage_event(
            session,
            obj,
            stage_type=payload.stage_type,
            event_date=event_date,
            source=payload.source,
            comment=payload.comment,
            raw_json={"source": payload.source, "work_session_id": work_session.id, "detail_data": payload.detail_data},
            created_by_user_id=user.id,
            work_session=work_session,
            detail_data=payload.detail_data,
            performers=payload.performers,
        )
        created += 1

    await write_audit(
        session,
        user,
        "work_session",
        work_session.id,
        "commit",
        None,
        {"object_count": len(objects), "stage_events_created": created, "stage_type": payload.stage_type, "blocked_no_object_count": blocked_count},
    )
    await session.commit()
    return WorkSessionCommitResponse(
        session_id=work_session.id,
        object_count=len(objects),
        stage_events_created=created,
    )


@router.get("/{session_id}", response_model=WorkSessionOut)
async def get_work_session(
    session_id: int,
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    result = await session.execute(
        select(WorkSession)
        .where(WorkSession.id == session_id)
        .options(
            selectinload(WorkSession.stage_events).selectinload(StageEvent.performers),
            selectinload(WorkSession.stage_events).selectinload(StageEvent.sample_prep_detail),
            selectinload(WorkSession.stage_events).selectinload(StageEvent.milling_detail),
            selectinload(WorkSession.stage_events).selectinload(StageEvent.dna_extraction_detail),
            selectinload(WorkSession.stage_events).selectinload(StageEvent.realtime_detail),
            selectinload(WorkSession.stage_events).selectinload(StageEvent.pcr_detail),
            selectinload(WorkSession.stage_events).selectinload(StageEvent.electrophoresis_detail),
            selectinload(WorkSession.stage_events).selectinload(StageEvent.analysis_detail),
        )
    )
    work_session = result.scalar_one_or_none()
    if not work_session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    return work_session


@router.post("/{session_id}/cancel", response_model=WorkSessionOut)
async def cancel_work_session(
    session_id: int,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    result = await session.execute(
        select(WorkSession)
        .where(WorkSession.id == session_id)
        .options(
            selectinload(WorkSession.stage_events).selectinload(StageEvent.performers),
            selectinload(WorkSession.stage_events).selectinload(StageEvent.sample_prep_detail),
            selectinload(WorkSession.stage_events).selectinload(StageEvent.milling_detail),
            selectinload(WorkSession.stage_events).selectinload(StageEvent.dna_extraction_detail),
            selectinload(WorkSession.stage_events).selectinload(StageEvent.realtime_detail),
            selectinload(WorkSession.stage_events).selectinload(StageEvent.pcr_detail),
            selectinload(WorkSession.stage_events).selectinload(StageEvent.electrophoresis_detail),
            selectinload(WorkSession.stage_events).selectinload(StageEvent.analysis_detail),
        )
    )
    work_session = result.scalar_one_or_none()
    if not work_session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    before = {"status": work_session.status}
    work_session.status = "cancelled"
    for event in work_session.stage_events:
        event.is_cancelled = True
    await write_audit(
        session,
        user,
        "work_session",
        work_session.id,
        "cancel",
        before,
        {"status": work_session.status, "stage_events_cancelled": len(work_session.stage_events)},
    )
    await session.commit()
    await session.refresh(work_session)
    return work_session
