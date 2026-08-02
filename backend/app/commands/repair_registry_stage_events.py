import argparse
import asyncio

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import User, UserRole
from app.services.registry import repair_registry_stage_events


async def main() -> None:
    parser = argparse.ArgumentParser(description="Reprocess registry Excel stage events for selected parties.")
    parser.add_argument("party_no", nargs="*", help="Party numbers to repair. If omitted, repairs all stored registries.")
    args = parser.parse_args()

    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.role == UserRole.admin, User.is_active.is_(True)).order_by(User.id)
        )
        user = result.scalars().first()
        stats = await repair_registry_stage_events(session, user, args.party_no or None)

    print(
        "Registry stage repair: "
        f"{stats['parties_repaired']}/{stats['parties_seen']} parties, "
        f"{stats['objects_matched']}/{stats['objects_seen']} objects matched, "
        f"{stats['events_deleted']} events deleted, "
        f"{stats['events_written']} events written, "
        f"{stats['skipped_rows']} rows skipped"
    )
    for party_no, party_stats in stats["parties"].items():
        print(
            f"  {party_no}: batch #{party_stats['batch_id']} {party_stats['filename']}: "
            f"{party_stats['objects_matched']} objects, "
            f"{party_stats['events_deleted']} deleted, "
            f"{party_stats['events_written']} written, "
            f"{party_stats['skipped_rows']} skipped"
        )
    for warning in stats["warnings"]:
        print(f"  warning: {warning}")


if __name__ == "__main__":
    asyncio.run(main())
