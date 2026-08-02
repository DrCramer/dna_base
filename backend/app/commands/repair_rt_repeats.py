import asyncio

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import User, UserRole
from app.services.rt import repair_rt_repeat_objects


async def main() -> None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.role == UserRole.admin, User.is_active.is_(True)).order_by(User.id)
        )
        user = result.scalars().first()
        stats = await repair_rt_repeat_objects(session, user)
    print(
        "RT repeat repair: "
        f"{stats['repeat_objects']} repeat objects, "
        f"{stats['rt_results_relinked']} RT results relinked, "
        f"{stats['stage_events_relinked']} stage events relinked, "
        f"{stats['affected_parties']} affected parties"
    )


if __name__ == "__main__":
    asyncio.run(main())
