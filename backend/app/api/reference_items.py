from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, db_session, edit_user
from app.models import ReferenceItem, User
from app.schemas import ReferenceItemCreate, ReferenceItemOut, ReferenceItemUpdate
from app.services.audit import write_audit


router = APIRouter(prefix="/reference-items", tags=["reference-items"])


def _snapshot(item: ReferenceItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "category": item.category,
        "name": item.name,
        "short_name": item.short_name,
        "comment": item.comment,
        "is_active": item.is_active,
    }


@router.get("", response_model=list[ReferenceItemOut])
async def list_reference_items(
    category: str | None = None,
    q: str | None = None,
    include_inactive: bool = False,
    limit: int = Query(default=1000, ge=1, le=5000),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(current_user),
):
    stmt = select(ReferenceItem)
    if category:
        stmt = stmt.where(ReferenceItem.category == category)
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                ReferenceItem.name.ilike(needle),
                ReferenceItem.short_name.ilike(needle),
                ReferenceItem.comment.ilike(needle),
                ReferenceItem.category.ilike(needle),
            )
        )
    if not include_inactive:
        stmt = stmt.where(ReferenceItem.is_active.is_(True))
    result = await session.execute(stmt.order_by(ReferenceItem.category, ReferenceItem.name).limit(limit))
    return list(result.scalars().all())


@router.post("", response_model=ReferenceItemOut)
async def create_reference_item(
    payload: ReferenceItemCreate,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    item = ReferenceItem(
        category=payload.category.strip(),
        name=payload.name.strip(),
        short_name=payload.short_name,
        comment=payload.comment,
        is_active=payload.is_active,
    )
    session.add(item)
    await session.flush()
    await write_audit(session, user, "reference_item", item.id, "create", None, _snapshot(item))
    await session.commit()
    await session.refresh(item)
    return item


@router.patch("/{item_id}", response_model=ReferenceItemOut)
async def update_reference_item(
    item_id: int,
    payload: ReferenceItemUpdate,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    item = await session.get(ReferenceItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Значение справочника не найдено")
    before = _snapshot(item)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if isinstance(value, str):
            value = value.strip()
        setattr(item, key, value)
    await write_audit(session, user, "reference_item", item.id, "update", before, _snapshot(item))
    await session.commit()
    await session.refresh(item)
    return item
