from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User


async def write_audit(
    session: AsyncSession,
    user: User | None,
    entity_type: str,
    entity_id: str | int,
    action: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    session.add(
        AuditLog(
            user_id=user.id if user else None,
            entity_type=entity_type,
            entity_id=str(entity_id),
            action=action,
            before_json=before,
            after_json=after,
        )
    )
