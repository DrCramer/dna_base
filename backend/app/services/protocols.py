from collections import defaultdict
from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Employee,
    LabProtocol,
    LabProtocolObject,
    LabProtocolStage,
    LabProtocolStagePerformer,
    LabProtocolWell,
    Party,
    ProtocolStageProfile,
    RegistryObject,
    RtResult,
    StageEvent,
)
from app.schemas import ProtocolPreviewRequest
from app.services.protocol_calculations import (
    calculate_dilution,
    calculate_electrophoresis_reagents,
    calculate_pcr_reagents,
)
from app.services.protocol_plate import build_protocol_layouts, natural_key, plate_capacity


STAGE_ORDER = ("dna_extraction", "realtime", "pcr", "electrophoresis")


async def suggested_protocol_meta(session: AsyncSession, protocol_date: date) -> dict[str, Any]:
    current = (
        await session.execute(
            select(func.max(LabProtocol.protocol_no)).where(LabProtocol.protocol_date == protocol_date)
        )
    ).scalar_one_or_none()
    number = int(current or 0) + 1
    return {
        "protocol_date": protocol_date,
        "suggested_no": number,
        "suggested_name": f"{protocol_date:%d-%m-%y}_{number}",
    }


async def protocol_object_snapshots(
    session: AsyncSession, object_ids: list[int]
) -> list[dict[str, Any]]:
    if not object_ids:
        return []
    rows = (
        await session.execute(
            select(RegistryObject, Party.party_no)
            .outerjoin(Party, Party.id == RegistryObject.party_id)
            .where(RegistryObject.id.in_(set(object_ids)), RegistryObject.status != "archived")
        )
    ).all()
    if len(rows) != len(set(object_ids)):
        raise HTTPException(status_code=400, detail="Часть выбранных объектов не найдена или находится в архиве")
    object_id_set = {obj.id for obj, _party_no in rows}
    latest_rt_ids = (
        select(RtResult.object_id, func.max(RtResult.id).label("max_id"))
        .where(RtResult.object_id.in_(object_id_set))
        .group_by(RtResult.object_id)
        .subquery()
    )
    rt_rows = (
        await session.execute(
            select(RtResult).join(latest_rt_ids, RtResult.id == latest_rt_ids.c.max_id)
        )
    ).scalars()
    rt_by_object = {row.object_id: row for row in rt_rows}
    stage_rows = (
        await session.execute(
            select(StageEvent.object_id, StageEvent.stage_type)
            .where(StageEvent.object_id.in_(object_id_set), StageEvent.is_cancelled.is_(False))
            .distinct()
        )
    ).all()
    stages: dict[int, list[str]] = defaultdict(list)
    for object_id, stage_type in stage_rows:
        stages[object_id].append(stage_type)

    snapshots = []
    for obj, joined_party_no in rows:
        rt = rt_by_object.get(obj.id)
        snapshots.append(
            {
                "id": obj.id,
                "party_id": obj.party_id,
                "party_no": joined_party_no or obj.party_no,
                "case_year": obj.case_year,
                "rcsme_reg_no": obj.rcsme_reg_no,
                "decree_no": obj.decree_no,
                "external_military_no": obj.external_military_no,
                "object_type": obj.object_type,
                "object_description": obj.object_description,
                "box_no": obj.box_no,
                "rt": (
                    {
                        "result_id": rt.id,
                        "concentration": rt.mean_quantity_ng_ul
                        if rt.mean_quantity_ng_ul is not None
                        else rt.quantity_ng_ul,
                        "ct_cq": rt.cq if rt.cq is not None else rt.ct,
                        "di": rt.degradation_index,
                    }
                    if rt
                    else None
                ),
                "stage_types": sorted(stages.get(obj.id, [])),
            }
        )
    return sorted(snapshots, key=lambda item: (natural_key(item["rcsme_reg_no"]), item["id"]))


async def _stage_snapshots(
    session: AsyncSession, payload: ProtocolPreviewRequest
) -> tuple[list[dict[str, Any]], dict[str, ProtocolStageProfile]]:
    profile_ids = {stage.profile_id for stage in payload.stages if stage.profile_id}
    profiles = {
        item.id: item
        for item in (
            await session.execute(select(ProtocolStageProfile).where(ProtocolStageProfile.id.in_(profile_ids)))
        ).scalars()
    } if profile_ids else {}
    employee_ids = {
        employee_id
        for stage in payload.stages
        for employee_id in [*stage.performer_ids, *[item.employee_id for item in stage.performers if item.employee_id]]
        if employee_id
    }
    employees = {
        item.id: item
        for item in (await session.execute(select(Employee).where(Employee.id.in_(employee_ids)))).scalars()
    } if employee_ids else {}

    output: list[dict[str, Any]] = []
    profiles_by_stage: dict[str, ProtocolStageProfile] = {}
    provided = {stage.stage_type: stage for stage in payload.stages}
    for stage_type in STAGE_ORDER:
        stage = provided.get(stage_type)
        if not stage:
            output.append({"stage_type": stage_type, "enabled": True, "work_date": payload.protocol_date.isoformat(), "profile_id": None, "kit_name": None, "sequencer_name": None, "comment": None, "performers": [], "settings": {}, "profile_snapshot": None})
            continue
        profile = profiles.get(stage.profile_id) if stage.profile_id else None
        if stage.profile_id and (not profile or profile.stage_type != stage_type):
            raise HTTPException(status_code=400, detail=f"Профиль не подходит для этапа {stage_type}")
        if profile:
            profiles_by_stage[stage_type] = profile
        seen: set[int | str] = set()
        performers = []
        requested = [*[{"employee_id": value} for value in stage.performer_ids], *[item.model_dump() for item in stage.performers]]
        for order_index, item in enumerate(requested):
            employee_id = item.get("employee_id")
            employee = employees.get(employee_id) if employee_id else None
            display_name = employee.full_name if employee else (item.get("display_name") or "").strip()
            identity: int | str = employee_id or display_name.casefold()
            if not display_name or identity in seen:
                continue
            seen.add(identity)
            performers.append({"employee_id": employee_id, "display_name": display_name, "role": item.get("role"), "order_index": order_index})
        output.append(
            {
                "stage_type": stage_type,
                "enabled": stage.enabled,
                "work_date": stage.work_date.isoformat() if stage.work_date else None,
                "profile_id": profile.id if profile else None,
                "kit_name": stage.kit_name or (profile.name if profile else None),
                "sequencer_name": stage.sequencer_name,
                "comment": stage.comment,
                "performers": performers,
                "settings": stage.settings,
                "profile_snapshot": (
                    {
                        "id": profile.id,
                        "name": profile.name,
                        "plate_rules": profile.plate_rules_json,
                        "reagent_config": profile.reagent_config_json,
                        "instrument_config": profile.instrument_config_json,
                    }
                    if profile
                    else None
                ),
            }
        )
    return output, profiles_by_stage


async def build_protocol_snapshot(
    session: AsyncSession, payload: ProtocolPreviewRequest
) -> dict[str, Any]:
    objects = await protocol_object_snapshots(session, payload.object_ids)
    stages, profiles = await _stage_snapshots(session, payload)
    rules = payload.plate_rules.model_dump()
    layouts = build_protocol_layouts(objects, rules)
    pcr_profile = profiles.get("pcr")
    electrophoresis_profile = profiles.get("electrophoresis")
    electrophoresis_stage = next(item for item in stages if item["stage_type"] == "electrophoresis")
    pcr_plates = layouts["pcr"]["plates"]
    calculations = {
        "pcr": [
            {
                "plate_index": plate["plate_index"],
                **calculate_pcr_reagents(
                    plate["sample_count"], pcr_profile.reagent_config_json if pcr_profile else {}
                ),
            }
            for plate in pcr_plates
        ],
        "electrophoresis": calculate_electrophoresis_reagents(
            len(objects),
            electrophoresis_profile.reagent_config_json if electrophoresis_profile else {},
            electrophoresis_stage["sequencer_name"],
        ),
    }
    dilution_settings = payload.dilution.model_dump()
    dilutions = []
    if payload.dilution.enabled:
        source_wells: dict[int, str] = {}
        for plate in layouts["source"]["plates"]:
            for well in plate["wells"]:
                if well["kind"] == "sample" and well["object_id"] is not None:
                    source_wells[well["object_id"]] = f"{plate['plate_index']}:{well['well']}"
        for obj in objects:
            concentration = obj["rt"]["concentration"] if obj.get("rt") else None
            dilutions.append(
                {
                    "object_id": obj["id"],
                    "display_name": obj["rcsme_reg_no"],
                    "well": source_wells.get(obj["id"]),
                    **calculate_dilution(
                        concentration,
                        target_concentration=payload.dilution.target_concentration,
                        source_dna_volume=payload.dilution.source_dna_volume,
                        dilution_one_volume=payload.dilution.dilution_one_volume,
                        threshold=payload.dilution.threshold,
                    ),
                }
            )
    missing_concentration = sum(1 for item in dilutions if not item["available"])
    warnings = list(layouts["warnings"])
    if missing_concentration:
        warnings.append(
            f"У {missing_concentration} объектов нет концентрации RT. Расчёт разведений для них недоступен."
        )
    snapshot = {
        "schema_version": 1,
        "protocol": {
            "protocol_date": payload.protocol_date.isoformat(),
            "protocol_no": payload.protocol_no,
            "name": payload.name.strip(),
            "comment": payload.comment,
        },
        "objects": [{**obj, "order_index": index} for index, obj in enumerate(objects)],
        "stages": stages,
        "plate_rules": rules,
        "layouts": layouts,
        "calculations": calculations,
        "dilution_settings": dilution_settings,
        "dilutions": dilutions,
        "warnings": warnings,
    }
    return {
        "selected_count": len(objects),
        "capacity": plate_capacity(rules),
        "max_capacity": 96,
        "objects": objects,
        "stages": stages,
        "layouts": layouts,
        "calculations": calculations,
        "dilutions": dilutions,
        "warnings": warnings,
        "snapshot": snapshot,
    }


async def replace_protocol_relations(
    session: AsyncSession, protocol: LabProtocol, snapshot: dict[str, Any]
) -> None:
    for model in (LabProtocolWell, LabProtocolObject, LabProtocolStage):
        await session.execute(delete(model).where(model.protocol_id == protocol.id))
    await session.flush()

    stage_ids: dict[str, int] = {}
    for stage in snapshot["stages"]:
        record = LabProtocolStage(
            protocol_id=protocol.id,
            stage_type=stage["stage_type"],
            enabled=stage["enabled"],
            work_date=date.fromisoformat(stage["work_date"]) if stage.get("work_date") else None,
            profile_id=stage.get("profile_id"),
            kit_name_snapshot=stage.get("kit_name"),
            sequencer_name_snapshot=stage.get("sequencer_name"),
            comment=stage.get("comment"),
            settings_json={
                **stage.get("settings", {}),
                "profile_snapshot": stage.get("profile_snapshot"),
            },
        )
        session.add(record)
        await session.flush()
        stage_ids[stage["stage_type"]] = record.id
        for performer in stage.get("performers", []):
            session.add(
                LabProtocolStagePerformer(
                    protocol_stage_id=record.id,
                    employee_id=performer.get("employee_id"),
                    display_name_snapshot=performer["display_name"],
                    role=performer.get("role"),
                    order_index=performer.get("order_index", 0),
                )
            )
    for obj in snapshot["objects"]:
        session.add(
            LabProtocolObject(
                protocol_id=protocol.id,
                object_id=obj["id"],
                party_id=obj.get("party_id"),
                order_index=obj["order_index"],
                rcsme_no_snapshot=obj.get("rcsme_reg_no"),
                decision_no_snapshot=obj.get("decree_no"),
                military_no_snapshot=obj.get("external_military_no"),
                object_type_snapshot=obj.get("object_type"),
                party_no_snapshot=obj.get("party_no"),
                box_no_snapshot=obj.get("box_no"),
                snapshot_json=obj,
            )
        )
    for layout_key, layout in snapshot["layouts"].items():
        if not isinstance(layout, dict) or "plates" not in layout:
            continue
        protocol_stage_id = stage_ids.get("pcr") if layout_key == "pcr" else None
        for plate in layout["plates"]:
            for well in plate["wells"]:
                session.add(
                    LabProtocolWell(
                        protocol_id=protocol.id,
                        protocol_stage_id=protocol_stage_id,
                        layout_key=layout_key,
                        plate_index=plate["plate_index"],
                        well=well["well"],
                        kind=well["kind"],
                        object_id=well.get("object_id"),
                        label=well.get("display_name") or well.get("label"),
                        order_index=well["order_index"],
                        snapshot_json=well,
                    )
                )
    await session.flush()
