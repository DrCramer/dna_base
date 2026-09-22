import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProtocolStageProfile, ReferenceItem


PROFILE_SOURCE = Path(__file__).resolve().parents[1] / "data" / "protocol_profiles_v13.json"


def _clean(value: Any) -> Any:
    return None if value in (None, "-") else value


def load_profile_rows() -> list[dict[str, Any]]:
    return json.loads(PROFILE_SOURCE.read_text(encoding="utf-8"))


async def seed_protocol_profiles(session: AsyncSession) -> int:
    rows = load_profile_rows()
    existing_refs = {
        (item.category, item.name): item
        for item in (
            await session.execute(
                select(ReferenceItem).where(
                    ReferenceItem.category.in_(("pcr_panel", "electrophoresis_kit", "sequencer"))
                )
            )
        ).scalars()
    }
    for category, name in (("sequencer", "GTZ G08"), ("sequencer", "GTZ G16"), ("sequencer", "GTZ G24"), ("sequencer", "SeqStudio")):
        if (category, name) not in existing_refs:
            item = ReferenceItem(category=category, name=name, is_active=True)
            session.add(item)
            existing_refs[(category, name)] = item
    await session.flush()

    existing_profiles = {
        (item.stage_type, item.name): item
        for item in (await session.execute(select(ProtocolStageProfile))).scalars()
    }
    created = 0
    for row in rows:
        name = str(row["СИСТЕМА"])
        pcr_reference = existing_refs.get(("pcr_panel", name))
        if not pcr_reference:
            pcr_reference = ReferenceItem(category="pcr_panel", name=name, is_active=True)
            session.add(pcr_reference)
            existing_refs[("pcr_panel", name)] = pcr_reference
        electrophoresis_reference = existing_refs.get(("electrophoresis_kit", name))
        if not electrophoresis_reference:
            electrophoresis_reference = ReferenceItem(category="electrophoresis_kit", name=name, is_active=True)
            session.add(electrophoresis_reference)
            existing_refs[("electrophoresis_kit", name)] = electrophoresis_reference
        await session.flush()

        pcr_config = {
            "master_mix": _clean(row.get("Master mix/Reaction mix/STR_BUF")),
            "primer": _clean(row.get("Primer")),
            "taq": _clean(row.get("TAQ")),
            "h2o": _clean(row.get("H20")),
            "mix_sample": _clean(row.get("Mix_sample")),
            "dna": _clean(row.get("V_DNA")),
            "pc": _clean(row.get("PC")),
        }
        electrophoresis_config = {
            "hidi_formamide": _clean(row.get("HiDi_Formamide")),
            "ils": _clean(row.get("ILS")),
            "mix_f_ils": _clean(row.get("Mix_F_ILS")),
            "ils_name": _clean(row.get("ILS_name")),
            "pcr_products": _clean(row.get("PCR_продукты")),
        }
        instrument_config = {
            "dye_set": _clean(row.get("DyeSet")),
            "injection_time": _clean(row.get("InjTime")),
            "run_time": _clean(row.get("RunTime")),
            "size_standard": _clean(row.get("SizeStandard")),
            "analysis_method": _clean(row.get("GMIDX_AnalysisMethod")),
            "panel": _clean(row.get("GMIDX_Panel")),
            "gmid_size_standard": _clean(row.get("GMIDX_SizeStandard")),
        }
        for stage_type, reference, reagent_config, instruments in (
            ("pcr", pcr_reference, pcr_config, {}),
            ("electrophoresis", electrophoresis_reference, electrophoresis_config, instrument_config),
        ):
            if (stage_type, name) in existing_profiles:
                continue
            profile = ProtocolStageProfile(
                stage_type=stage_type,
                name=name,
                reference_item_id=reference.id,
                active=True,
                plate_rules_json={},
                reagent_config_json=reagent_config,
                instrument_config_json=instruments,
            )
            session.add(profile)
            existing_profiles[(stage_type, name)] = profile
            created += 1
    await session.commit()
    return created
