import asyncio

from app.db.session import SessionLocal
from app.services.dictionaries import seed_lab_dictionaries


async def main() -> None:
    async with SessionLocal() as session:
        stats = await seed_lab_dictionaries(session)
    print(
        "Seeded dictionaries: "
        f"{stats['employees_active']} active employees, "
        f"{stats['employees_disabled']} disabled employees, "
        f"{stats['references_active']} active reference items, "
        f"{stats['references_disabled']} disabled reference items"
    )


if __name__ == "__main__":
    asyncio.run(main())
