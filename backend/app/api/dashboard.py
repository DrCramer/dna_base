from fastapi import APIRouter, Depends
from sqlalchemy import Integer, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, db_session
from app.models import Party, RegistryImportBatch, RegistryObject, RtResult, StageEvent, User


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
async def dashboard(session: AsyncSession = Depends(db_session), _user: User = Depends(current_user)):
    total = (
        await session.execute(select(func.count(RegistryObject.id)).where(RegistryObject.status != "archived"))
    ).scalar_one()
    imported = (await session.execute(select(func.count(RegistryImportBatch.id)))).scalar_one()
    active_parties_count = (
        await session.execute(select(func.count(Party.id)).where(Party.status != "archived"))
    ).scalar_one()
    archived_parties_count = (
        await session.execute(select(func.count(Party.id)).where(Party.status == "archived"))
    ).scalar_one()
    rt_unmatched = (
        await session.execute(select(func.count(RtResult.id)).where(RtResult.object_id.is_(None)))
    ).scalar_one()
    active_party_ids = select(Party.id).where(Party.status != "archived")
    active_objects_stmt = select(RegistryObject.id).where(
        RegistryObject.party_id.in_(active_party_ids),
        RegistryObject.status != "archived",
    )
    active_objects_total = (
        await session.execute(
            select(func.count(RegistryObject.id)).where(
                RegistryObject.party_id.in_(active_party_ids),
                RegistryObject.status != "archived",
            )
        )
    ).scalar_one()
    completed_objects = (
        await session.execute(
            select(func.count(func.distinct(StageEvent.object_id)))
            .join(RegistryObject, RegistryObject.id == StageEvent.object_id)
            .where(
                RegistryObject.party_id.in_(active_party_ids),
                RegistryObject.status != "archived",
                StageEvent.is_cancelled.is_(False),
            )
        )
    ).scalar_one()
    objects_without_events = max(int(active_objects_total) - int(completed_objects), 0)
    stage_rows = await session.execute(
        select(StageEvent.stage_type, func.count(func.distinct(StageEvent.object_id)))
        .join(RegistryObject, RegistryObject.id == StageEvent.object_id)
        .where(
            RegistryObject.id.in_(active_objects_stmt),
            StageEvent.is_cancelled.is_(False),
        )
        .group_by(StageEvent.stage_type)
    )
    stage_summary = {stage_type: int(count) for stage_type, count in stage_rows.all()}
    party_object_rows = await session.execute(
        select(RegistryObject.party_id, func.count(RegistryObject.id))
        .where(RegistryObject.party_id.in_(active_party_ids), RegistryObject.status != "archived")
        .group_by(RegistryObject.party_id)
    )
    party_object_counts = {party_id: int(count) for party_id, count in party_object_rows.all()}
    party_stage_rows = await session.execute(
        select(RegistryObject.party_id, StageEvent.stage_type, func.count(func.distinct(StageEvent.object_id)))
        .join(StageEvent, StageEvent.object_id == RegistryObject.id)
        .where(
            RegistryObject.party_id.in_(active_party_ids),
            RegistryObject.status != "archived",
            StageEvent.is_cancelled.is_(False),
        )
        .group_by(RegistryObject.party_id, StageEvent.stage_type)
    )
    party_stage_counts: dict[int, dict[str, int]] = {}
    for party_id, stage_type, count in party_stage_rows.all():
        party_stage_counts.setdefault(party_id, {})[stage_type] = int(count)
    numeric_party_no = case(
        (Party.party_no.op("~")(r"^\d+$"), Party.party_no.cast(Integer)),
        else_=None,
    )
    parties_result = await session.execute(
        select(Party)
        .where(Party.status != "archived")
        .order_by(numeric_party_no.desc().nullslast(), Party.party_no.desc(), Party.id.desc())
        .limit(15)
    )
    control_parties_result = await session.execute(
        select(Party)
        .where(
            Party.status != "archived",
            or_(
                Party.control_actual_decrees.is_not(None),
                Party.control_unidentified_rostov_no.is_not(None),
                Party.control_decree_without_object.is_not(None),
                Party.control_object_without_decree.is_not(None),
                Party.control_need_recall.is_not(None),
                Party.control_recalled.is_not(None),
            ),
        )
        .order_by(numeric_party_no.desc().nullslast(), Party.party_no.desc(), Party.id.desc())
    )
    latest = await session.execute(
        select(RegistryImportBatch).order_by(RegistryImportBatch.id.desc()).limit(5)
    )

    def party_payload(party: Party) -> dict:
        return {
            "id": party.id,
            "party_no": party.party_no,
            "case_year": party.case_year,
            "object_count": party_object_counts.get(party.id, 0),
            "stage_counts": party_stage_counts.get(party.id, {}),
            "control_actual_decrees": party.control_actual_decrees,
            "control_unidentified_rostov_no": party.control_unidentified_rostov_no,
            "control_decree_without_object": party.control_decree_without_object,
            "control_object_without_decree": party.control_object_without_decree,
            "control_need_recall": party.control_need_recall,
            "control_recalled": party.control_recalled,
        }

    return {
        "total_objects": total,
        "active_parties": active_parties_count,
        "archived_parties": archived_parties_count,
        "active_objects": active_objects_total,
        "objects_without_events": objects_without_events,
        "import_batches": imported,
        "rt_unmatched": rt_unmatched,
        "electrophoresis_pdf_unmatched": 0,
        "stage_summary": stage_summary,
        "active_party_progress": [party_payload(party) for party in parties_result.scalars().all()],
        "control_party_progress": [party_payload(party) for party in control_parties_result.scalars().all()],
        "latest_imports": [
            {
                "id": batch.id,
                "filename": batch.original_filename,
                "party_no": batch.party_no,
                "rows_imported": batch.rows_imported,
                "imported_at": batch.imported_at,
            }
            for batch in latest.scalars().all()
        ],
    }
