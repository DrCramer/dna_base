from dataclasses import dataclass
from datetime import date
from typing import Iterable

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.models import RealtimeDetail, StageEvent


@dataclass(frozen=True)
class LatestRealtimeDetail:
    event_id: int
    detail: RealtimeDetail | None


def _event_order_key(event: StageEvent) -> tuple[int, date, int]:
    return event.attempt_no or 0, event.event_date or date.min, event.id or 0


def pick_latest_realtime_event(events: Iterable[StageEvent]) -> StageEvent | None:
    active = [
        event
        for event in events
        if event.stage_type == "realtime" and not event.is_cancelled
    ]
    return max(active, key=_event_order_key, default=None)


async def get_latest_realtime_details(
    session: AsyncSession, object_ids: Iterable[int]
) -> dict[int, LatestRealtimeDetail]:
    ids = set(object_ids)
    if not ids:
        return {}
    events = list(
        (
            await session.execute(
                select(StageEvent)
                .options(selectinload(StageEvent.realtime_detail))
                .where(
                    StageEvent.object_id.in_(ids),
                    StageEvent.stage_type == "realtime",
                    StageEvent.is_cancelled.is_(False),
                )
            )
        ).scalars()
    )
    grouped: dict[int, list[StageEvent]] = {}
    for event in events:
        grouped.setdefault(event.object_id, []).append(event)
    result: dict[int, LatestRealtimeDetail] = {}
    for object_id, object_events in grouped.items():
        latest = pick_latest_realtime_event(object_events)
        if latest:
            result[object_id] = LatestRealtimeDetail(
                event_id=latest.id,
                detail=latest.realtime_detail,
            )
    return result


def latest_realtime_has_small_quantity(
    object_id: ColumnElement[int],
) -> ColumnElement[bool]:
    latest_event_id = (
        select(StageEvent.id)
        .where(
            StageEvent.object_id == object_id,
            StageEvent.stage_type == "realtime",
            StageEvent.is_cancelled.is_(False),
        )
        .order_by(
            StageEvent.attempt_no.desc(),
            StageEvent.event_date.desc().nullslast(),
            StageEvent.id.desc(),
        )
        .limit(1)
        .scalar_subquery()
    )
    return exists(
        select(RealtimeDetail.id).where(
            RealtimeDetail.stage_event_id == latest_event_id,
            RealtimeDetail.small_quantity.is_not(None),
        )
    )
