"""Искусственные объекты и рецептуры только для изолированной E2E-базы."""
import asyncio
from datetime import date

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import Party, RegistryObject, StageEvent, RealtimeDetail, ProtocolStageProfile


async def main():
    if not (make_url(get_settings().database_url).database or "").startswith("dna_genetic_test_"):
        raise RuntimeError("Запуск допускается только в изолированной тестовой БД")
    async with SessionLocal() as session:
        party = (await session.execute(select(Party).where(Party.party_no == "9900", Party.case_year == date.today().year))).scalar_one_or_none()
        if party:
            return
        party = Party(party_no="9900", case_year=date.today().year, object_count=4)
        session.add(party)
        await session.flush()
        for index, quantity in enumerate([10, 1000, 0.4, None]):
            obj = RegistryObject(party_id=party.id, party_no=party.party_no, case_year=party.case_year, rcsme_reg_no=f"{990010 + index}-1", rcsme_reg_no_base=str(990010 + index))
            session.add(obj)
            await session.flush()
            event = StageEvent(object_id=obj.id, stage_type="realtime", event_date=date.today())
            session.add(event)
            await session.flush()
            session.add(RealtimeDetail(stage_event_id=event.id, small_quantity=quantity, long_quantity=quantity * 2 if quantity else 5, y_quantity=quantity / 2 if quantity else 2))
        for dna in (1, 15):
            session.add(ProtocolStageProfile(stage_type="pcr", name=f"Тест: DNA {dna}", reagent_config_json={"master_mix": 5, "h2o": 2, "dna": dna}, plate_rules_json={}, instrument_config_json={}))
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
