from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import current_user, db_session
from app.models import RegistryObject, StageEvent, User
from app.services.export import build_registry_workbook


router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/registry.xlsx")
async def export_registry(
    q: str | None = None,
    party_no: str | None = None,
    year: int | None = None,
    limit: int = 5000,
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
        .order_by(RegistryObject.id)
        .limit(min(limit, 20000))
    )
    if q:
        needle = f"%{q}%"
        stmt = stmt.where(
            RegistryObject.rcsme_reg_no.ilike(needle)
            | RegistryObject.party_no.ilike(needle)
            | RegistryObject.decree_no.ilike(needle)
            | RegistryObject.object_description.ilike(needle)
        )
    if party_no:
        stmt = stmt.where(RegistryObject.party_no == party_no.strip())
    if year is not None:
        stmt = stmt.where(RegistryObject.case_year == year)
    result = await session.execute(stmt)
    content = build_registry_workbook(list(result.scalars().all()))
    headers = {"Content-Disposition": 'attachment; filename="registry.xlsx"'}
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )
