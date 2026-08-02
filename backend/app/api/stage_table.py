from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import current_user, db_session, edit_user
from app.models import RegistryObject, StageEvent, User, WorkSession, WorkSessionObject
from app.schemas import (
    StageEventsApplyRequest,
    StageEventsApplyResponse,
    StageEventsInlineApplyRequest,
    StageEventsInlineApplyResponse,
    StageEventsPreviewRequest,
    StageEventsPreviewResponse,
    StageTableQueryRequest,
    StageTableResponse,
)
from app.services.audit import write_audit
from app.services.no_object import object_is_no_object, party_no_object_controls
from app.services.stage_table import build_stage_table, public_to_canonical, select_stage_table_objects
from app.services.stages import create_stage_event, update_stage_event_data


router = APIRouter(tags=["stage-table"])


STAGE_DATE_FIELDS = {
    "sample_prep": ("washing_date", "bone_tissue_date"),
    "milling": ("milling_date",),
    "dna_extraction": ("extraction_date",),
    "realtime": ("quant_date",),
    "pcr": ("pcr_date",),
    "electrophoresis": ("electrophoresis_date",),
    "analysis": ("analysis_date",),
}


def _parse_date(value: Any) -> date | Any:
    if isinstance(value, date) or value in (None, ""):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return value
    return value


def _normalized_detail(stage_type: str, detail_data: dict[str, Any]) -> dict[str, Any]:
    detail = dict(detail_data or {})
    if stage_type == "analysis" and "analysis_status" in detail and "status" not in detail:
        detail["status"] = detail.pop("analysis_status")
    for field in STAGE_DATE_FIELDS.get(stage_type, ()):
        if field in detail:
            detail[field] = _parse_date(detail[field])
    return detail


def _detail_from_event(event: StageEvent | None, stage_type: str) -> dict[str, Any]:
    if not event:
        return {}
    if stage_type == "sample_prep" and event.sample_prep_detail:
        detail = event.sample_prep_detail
        return {
            "registry_filled_by": detail.registry_filled_by,
            "photo_performers": detail.photo_performers,
            "photo_assistants": detail.photo_assistants,
            "washing_performers": detail.washing_performers,
            "washing_assistants": detail.washing_assistants,
            "washing_date": detail.washing_date,
            "bone_tissue_performers": detail.bone_tissue_performers,
            "bone_tissue_date": detail.bone_tissue_date,
        }
    if stage_type == "milling" and event.milling_detail:
        detail = event.milling_detail
        return {"milling_performers": detail.milling_performers, "cups": detail.cups, "milling_date": detail.milling_date}
    if stage_type == "dna_extraction" and event.dna_extraction_detail:
        detail = event.dna_extraction_detail
        return {"extraction_date": detail.extraction_date, "extraction_method": detail.extraction_method}
    if stage_type == "realtime" and event.realtime_detail:
        detail = event.realtime_detail
        return {
            "quant_method": detail.quant_method,
            "quant_date": detail.quant_date,
            "quant_performer": detail.quant_performer,
            "pipetting_method": detail.pipetting_method,
            "concentration": detail.concentration,
            "ct_cq": detail.ct_cq,
            "di": detail.di,
            "ipc": detail.ipc,
            "long_quantity": detail.long_quantity,
            "small_quantity": detail.small_quantity,
            "y_quantity": detail.y_quantity,
            "comment": detail.comment,
        }
    if stage_type == "pcr" and event.pcr_detail:
        detail = event.pcr_detail
        return {
            "pcr_date": detail.pcr_date,
            "locus_panel": detail.locus_panel,
            "pipetting_method": detail.pipetting_method,
            "normalization_performers": detail.normalization_performers,
            "pcr_performers": detail.pcr_performers,
        }
    if stage_type == "electrophoresis" and event.electrophoresis_detail:
        detail = event.electrophoresis_detail
        return {
            "electrophoresis_date": detail.electrophoresis_date,
            "sequencer": detail.sequencer,
            "pipetting_method": detail.pipetting_method,
            "performers": detail.performers,
        }
    if stage_type == "analysis" and event.analysis_detail:
        detail = event.analysis_detail
        return {"genotype": detail.genotype, "analysis_date": detail.analysis_date, "status": detail.status}
    return {}


async def _latest_stage_event(session: AsyncSession, object_id: int, stage_type: str) -> StageEvent | None:
    result = await session.execute(
        select(StageEvent)
        .options(
            selectinload(StageEvent.performers),
            selectinload(StageEvent.sample_prep_detail),
            selectinload(StageEvent.milling_detail),
            selectinload(StageEvent.dna_extraction_detail),
            selectinload(StageEvent.realtime_detail),
            selectinload(StageEvent.pcr_detail),
            selectinload(StageEvent.electrophoresis_detail),
            selectinload(StageEvent.analysis_detail),
        )
        .where(
            StageEvent.object_id == object_id,
            StageEvent.stage_type == stage_type,
            StageEvent.is_cancelled.is_(False),
        )
        .order_by(StageEvent.attempt_no.desc(), StageEvent.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _merge_detail(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        merged[key] = None if value == "" else value
    return merged


PERFORMER_DETAIL_KEYS = {
    "sample_prep": {
        "photo_performers",
        "photo_assistants",
        "washing_performers",
        "washing_assistants",
        "bone_tissue_performers",
    },
    "milling": {"milling_performers", "cups"},
    "dna_extraction": {"extraction_performers"},
    "realtime": {"quant_performer"},
    "pcr": {"normalization_performers", "pcr_performers"},
    "electrophoresis": {"performers", "performer_1", "performer_2", "extra_performers"},
    "analysis": {"analysis_performers"},
}


def _performers_touched(stage_type: str, detail_data: dict[str, Any]) -> bool:
    return bool(PERFORMER_DETAIL_KEYS.get(stage_type, set()).intersection(detail_data.keys()))


def _event_snapshot(event: StageEvent | None, stage_type: str) -> dict[str, Any] | None:
    if not event:
        return None
    return {
        "id": event.id,
        "object_id": event.object_id,
        "stage_type": event.stage_type,
        "attempt_no": event.attempt_no,
        "event_date": event.event_date.isoformat() if event.event_date else None,
        "comment": event.comment,
        "detail_data": _detail_from_event(event, stage_type),
        "performers": [
            {"employee_id": item.employee_id, "raw_name": item.raw_name, "role": item.role}
            for item in sorted(event.performers or [], key=lambda performer: performer.order_index)
        ],
    }


def _event_date(stage_type: str, work_date: date | None, detail_data: dict[str, Any]) -> date | None:
    if work_date:
        return work_date
    for field in STAGE_DATE_FIELDS.get(stage_type, ()):
        value = detail_data.get(field)
        if isinstance(value, date):
            return value
    return None


async def _selected_objects(
    session: AsyncSession,
    payload: StageEventsPreviewRequest,
    *,
    include_archived: bool = False,
) -> list[RegistryObject]:
    if payload.object_ids:
        stmt = (
            select(RegistryObject)
            .options(selectinload(RegistryObject.parent_object))
            .where(RegistryObject.id.in_(payload.object_ids))
            .order_by(RegistryObject.id)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
    if payload.party_ids:
        return await select_stage_table_objects(
            session,
            party_ids=payload.party_ids,
            q=payload.q,
            include_archived=include_archived,
        )
    return []


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
    session: AsyncSession,
    object_ids: list[int],
    stage_type: str,
) -> dict[int, int]:
    if not object_ids:
        return {}
    result = await session.execute(
        select(StageEvent.object_id, func.count(StageEvent.id))
        .where(
            StageEvent.object_id.in_(object_ids),
            StageEvent.stage_type == stage_type,
            StageEvent.is_cancelled.is_(False),
        )
        .group_by(StageEvent.object_id)
    )
    return {object_id: int(count) for object_id, count in result.all()}


def _filled_fields(detail_data: dict[str, Any], performers: list[dict[str, Any]], comment: str | None) -> list[str]:
    fields = [key for key, value in detail_data.items() if value not in (None, "", [])]
    if performers:
        fields.append("performers")
    if comment:
        fields.append("comment")
    return fields


@router.get("/parties/{party_id}/stage-table/{stage_type}", response_model=StageTableResponse)
async def party_stage_table(
    party_id: int,
    stage_type: str,
    q: str | None = None,
    quick: str | None = Query(default=None),
    show_history: bool = False,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    return await build_stage_table(
        session,
        party_ids=[party_id],
        stage_type=stage_type,
        q=q,
        filters={"quick": quick} if quick else {},
        show_history=show_history,
        limit=limit,
        offset=offset,
    )


@router.post("/stage-table/query", response_model=StageTableResponse)
async def query_stage_table(
    payload: StageTableQueryRequest,
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    return await build_stage_table(
        session,
        party_ids=payload.party_ids,
        stage_type=payload.stage_type,
        q=payload.q,
        filters=payload.filters,
        include_archived=payload.include_archived,
        show_history=payload.show_history,
        limit=payload.limit,
        offset=payload.offset,
    )


@router.post("/stage-events/preview", response_model=StageEventsPreviewResponse)
async def preview_stage_events(
    payload: StageEventsPreviewRequest,
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(edit_user),
):
    stage_type = public_to_canonical(payload.stage_type)
    if stage_type in ("registration", "all"):
        raise HTTPException(status_code=400, detail="Для этого представления нельзя создать этап")
    selected_objects = await _selected_objects(session, payload)
    objects, blocked_count = await _editable_stage_objects(session, selected_objects, stage_type)
    existing_counts = await _existing_stage_counts(session, [obj.id for obj in objects], stage_type)
    next_attempts = [existing_counts.get(obj.id, 0) + 1 for obj in objects] or [1]
    warnings = []
    if not objects:
        warnings.append("Не выбраны объекты для массового заполнения.")
    if blocked_count:
        warnings.append(f"Пропущено объектов с отметкой «Нет объекта»: {blocked_count}.")
    sample_party_ids = payload.party_ids
    if payload.object_ids:
        sample_party_ids = sorted({obj.party_id for obj in objects if obj.party_id})
    sample_table = await build_stage_table(
        session,
        party_ids=sample_party_ids,
        stage_type=stage_type,
        q=payload.q,
        filters=payload.filters,
    )
    selected = {obj.id for obj in objects}
    sample_table.rows = [row for row in sample_table.rows if row.object.id in selected][:20]
    return StageEventsPreviewResponse(
        object_count=len(objects),
        stage_type=stage_type,
        objects_with_existing_stage=sum(1 for obj in objects if existing_counts.get(obj.id, 0) > 0),
        objects_without_stage=sum(1 for obj in objects if existing_counts.get(obj.id, 0) == 0),
        next_attempt_min=min(next_attempts),
        next_attempt_max=max(next_attempts),
        filled_fields=_filled_fields(payload.detail_data, payload.performers, payload.comment),
        warnings=warnings,
        sample_rows=sample_table.rows,
    )


@router.post("/stage-events/apply", response_model=StageEventsApplyResponse)
async def apply_stage_events(
    payload: StageEventsApplyRequest,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    stage_type = public_to_canonical(payload.stage_type)
    if stage_type in ("registration", "all"):
        raise HTTPException(status_code=400, detail="Для этого представления нельзя создать этап")
    selected_objects = await _selected_objects(session, payload)
    objects, blocked_count = await _editable_stage_objects(session, selected_objects, stage_type)
    if not objects:
        if blocked_count:
            raise HTTPException(status_code=400, detail="Все выбранные объекты помечены как «Нет объекта»")
        raise HTTPException(status_code=400, detail="Не выбраны объекты для массового заполнения")
    detail_data = _normalized_detail(stage_type, payload.detail_data)
    party_id = payload.party_ids[0] if len(payload.party_ids) == 1 else None
    work_session = WorkSession(
        party_id=party_id,
        stage_type=stage_type,
        title=payload.title or "Массовое заполнение этапа",
        work_date=payload.work_date,
        comment=payload.comment,
        created_by_user_id=user.id,
            source=payload.source,
            status="applied",
            raw_json={**payload.model_dump(mode="json"), "blocked_no_object_count": blocked_count},
    )
    session.add(work_session)
    await session.flush()

    event_date = _event_date(stage_type, payload.work_date, detail_data)
    created = 0
    updated = 0
    update_mode = payload.apply_mode == "update_latest"
    performers_touched = bool(payload.performers) or _performers_touched(stage_type, detail_data)
    comment_touched = payload.comment is not None
    for index, obj in enumerate(objects):
        session.add(
            WorkSessionObject(
                work_session_id=work_session.id,
                object_id=obj.id,
                object_order=index,
                is_excluded=False,
            )
        )
        latest = await _latest_stage_event(session, obj.id, stage_type) if update_mode else None
        if latest:
            before = _event_snapshot(latest, stage_type)
            merged_detail = _merge_detail(_detail_from_event(latest, stage_type), detail_data)
            await update_stage_event_data(
                session,
                latest,
                stage_type=stage_type,
                event_date=event_date,
                comment=payload.comment,
                comment_touched=comment_touched,
                raw_json={
                    "source": latest.source,
                    "last_ui_action": "mass_update_latest",
                    "last_detail_data": payload.detail_data,
                    "last_work_session_id": work_session.id,
                },
                detail_data=merged_detail,
                performers=payload.performers,
                performers_touched=performers_touched,
            )
            updated += 1
            await write_audit(
                session,
                user,
                "stage_event",
                latest.id,
                "mass_update_latest",
                before,
                _event_snapshot(latest, stage_type),
            )
        else:
            await create_stage_event(
                session,
                obj,
                stage_type=stage_type,
                event_date=event_date,
                source=payload.source,
                comment=payload.comment,
                raw_json={
                    "source": payload.source,
                    "ui_action": "mass_fill_update_latest" if update_mode else "mass_fill",
                    "detail_data": payload.detail_data,
                    "work_session_id": work_session.id,
                },
                created_by_user_id=user.id,
                work_session=work_session,
                detail_data=detail_data,
                performers=payload.performers,
            )
            created += 1

    await write_audit(
        session,
        user,
        "stage_events",
        str(work_session.id),
        "mass_update_latest" if update_mode else "mass_apply",
        None,
        {
            "object_count": len(objects),
            "stage_events_created": created,
            "stage_events_updated": updated,
            "stage_type": stage_type,
            "blocked_no_object_count": blocked_count,
        },
    )
    await session.commit()
    return StageEventsApplyResponse(
        session_id=work_session.id,
        object_count=len(objects),
        stage_events_created=created,
        stage_events_updated=updated,
    )


@router.post("/stage-events/apply-inline", response_model=StageEventsInlineApplyResponse)
async def apply_inline_stage_event(
    payload: StageEventsInlineApplyRequest,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    stage_type = public_to_canonical(payload.stage_type)
    if stage_type in ("registration", "all"):
        raise HTTPException(status_code=400, detail="Для этого представления нельзя создать этап")
    obj_result = await session.execute(
        select(RegistryObject)
        .options(selectinload(RegistryObject.parent_object))
        .where(RegistryObject.id == payload.object_id)
    )
    obj = obj_result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="Объект не найден")
    controls = await party_no_object_controls(session, [obj.party_id] if obj.party_id else [])
    if object_is_no_object(obj, controls.get(obj.party_id or 0, set())):
        raise HTTPException(status_code=400, detail="Объект помечен как «Нет объекта». Ввод данных на последующих этапах заблокирован.")
    latest = await _latest_stage_event(session, obj.id, stage_type)
    normalized_patch = _normalized_detail(stage_type, payload.detail_data)
    detail_data = _merge_detail(_detail_from_event(latest, stage_type), normalized_patch)
    performers = payload.performers
    if not performers and latest and not _performers_touched(stage_type, normalized_patch):
        performers = [
            {"employee_id": item.employee_id, "raw_name": item.raw_name, "role": item.role}
            for item in sorted(latest.performers or [], key=lambda performer: performer.order_index)
        ]
    comment_touched = "comment" in payload.model_fields_set
    event_comment = payload.comment if comment_touched else (latest.comment if latest else None)
    event = await create_stage_event(
        session,
        obj,
        stage_type=stage_type,
        event_date=_event_date(stage_type, None, detail_data),
        source=payload.source,
        comment=event_comment,
        raw_json={"source": payload.source, "ui_action": "inline_edit", "detail_data": payload.detail_data, "merged_detail_data": detail_data},
        created_by_user_id=user.id,
        detail_data=detail_data,
        performers=performers,
    )
    await write_audit(
        session,
        user,
        "stage_event",
        event.id,
        "inline_apply",
        None,
        {"object_id": obj.id, "stage_type": stage_type, "attempt_no": event.attempt_no},
    )
    await session.commit()
    return StageEventsInlineApplyResponse(
        event_id=event.id,
        object_id=obj.id,
        stage_type=stage_type,
        attempt_no=event.attempt_no,
    )
