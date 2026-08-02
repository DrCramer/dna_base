from datetime import datetime, time
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, RegistryObject, RtResult, RtRun, StageEvent, User
from app.parsers.normalization import normalize_lab_sample, number_base
from app.parsers.rt import parse_rt_preview
from app.services.audit import write_audit
from app.services.registry import recalculate_party_counts
from app.services.repeats import ensure_repeat_object
from app.services.stages import create_stage_event


def _row_sample_for_binding(row: dict[str, Any]) -> str | None:
    return row.get("normalized_sample_name") or row.get("sample_name_raw") or row.get("sample_object_no")


async def _resolve_sample_object(
    session: AsyncSession,
    sample_value: str | None,
    *,
    user: User | None = None,
    create_repeat: bool = False,
) -> RegistryObject | None:
    lab_sample = normalize_lab_sample(sample_value)
    if not lab_sample.normalized:
        return None
    result = await session.execute(select(RegistryObject).where(RegistryObject.rcsme_reg_no == lab_sample.normalized))
    exact_matches = list(result.scalars().all())
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        return None
    if lab_sample.repeat_suffix and lab_sample.object_no:
        parent_result = await session.execute(select(RegistryObject).where(RegistryObject.rcsme_reg_no == lab_sample.object_no))
        parents = list(parent_result.scalars().all())
        if len(parents) != 1:
            return None
        parent = parents[0]
        if create_repeat:
            return await ensure_repeat_object(session, parent, lab_sample, user, source="rt_import")
        return parent
    result = await session.execute(
        select(RegistryObject).where(
            or_(
                RegistryObject.decree_no == lab_sample.normalized,
                RegistryObject.rcsme_reg_no_base == lab_sample.base,
                RegistryObject.decree_no_base == lab_sample.base,
            )
        )
    )
    matches = list(result.scalars().all())
    return matches[0] if len(matches) == 1 else None


async def match_rt_rows(session: AsyncSession, rows: list[dict[str, Any]]) -> dict[str, int | None]:
    object_numbers: set[str] = set()
    bases: set[str] = set()
    samples: set[str] = set()
    for row in rows:
        sample = _row_sample_for_binding(row)
        lab_sample = normalize_lab_sample(sample)
        if lab_sample.object_no:
            object_numbers.add(lab_sample.object_no)
        if lab_sample.base:
            bases.add(lab_sample.base)
        if row.get("normalized_sample_name"):
            samples.add(row["normalized_sample_name"])
    if not bases and not samples and not object_numbers:
        return {}
    result = await session.execute(
        select(RegistryObject).where(
            or_(
                RegistryObject.rcsme_reg_no.in_(samples),
                RegistryObject.rcsme_reg_no.in_(object_numbers),
                RegistryObject.decree_no.in_(samples),
                RegistryObject.decree_no.in_(object_numbers),
                RegistryObject.rcsme_reg_no_base.in_(bases),
                RegistryObject.decree_no_base.in_(bases),
            )
        )
    )
    mapping: dict[str, int | None] = {}
    seen: dict[str, int] = {}
    for obj in result.scalars().all():
        for key in [obj.rcsme_reg_no, obj.decree_no, obj.rcsme_reg_no_base, obj.decree_no_base]:
            if not key:
                continue
            if key in seen and seen[key] != obj.id:
                mapping[key] = None
            else:
                seen[key] = obj.id
                mapping[key] = obj.id
    return mapping


async def rt_preview_rows_with_matches(session: AsyncSession, rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, int]:
    matched = 0
    preview_rows: list[dict[str, Any]] = []
    for row in rows:
        sample = _row_sample_for_binding(row)
        lab_sample = normalize_lab_sample(sample)
        obj = await _resolve_sample_object(session, lab_sample.normalized)
        repeat_object_exists = bool(obj and lab_sample.repeat_suffix and obj.rcsme_reg_no == lab_sample.normalized)
        if obj:
            matched += 1
        preview_rows.append(
            {
                **row,
                "object_id": obj.id if obj else None,
                "matched": bool(obj),
                "object_rcsme_reg_no": lab_sample.normalized if obj and lab_sample.repeat_suffix else (obj.rcsme_reg_no if obj else None),
                "object_decree_no": obj.decree_no if obj else None,
                "party_no": obj.party_no if obj else None,
                "is_repeat_sample": bool(lab_sample.repeat_suffix),
                "repeat_suffix": lab_sample.repeat_suffix,
                "parent_rcsme_reg_no": lab_sample.object_no if lab_sample.repeat_suffix else None,
                "repeat_object_exists": repeat_object_exists,
                "will_create_repeat_object": bool(obj and lab_sample.repeat_suffix and not repeat_object_exists),
            }
        )
    existing = await rt_existing_import_summary(session, preview_rows)
    existing_by_identity = {item["sample_identity"] for item in existing["existing_rt_samples"]}
    existing_by_object = set(existing["existing_object_ids"])
    for row in preview_rows:
        identity = _sample_identity(row)
        repeat_needs_parent = bool(row.get("is_repeat_sample") and not row.get("repeat_object_exists"))
        row["has_existing_rt"] = bool(identity in existing_by_identity or (row.get("object_id") in existing_by_object and not repeat_needs_parent))
    return preview_rows, matched, max(len(rows) - matched, 0)


def _round4(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


async def _delete_previous_rt_import(session: AsyncSession, file_sha256: str) -> None:
    result = await session.execute(select(RtRun).where(RtRun.raw_json["file_sha256"].as_string() == file_sha256))
    for run in result.scalars().all():
        await session.delete(run)
    event_result = await session.execute(
        select(StageEvent).where(
            StageEvent.source == "rt_import",
            StageEvent.raw_json["source_file_sha256"].as_string() == file_sha256,
        )
    )
    for event in event_result.scalars().all():
        await session.delete(event)


def _sample_identity(row: dict[str, Any]) -> str | None:
    sample = _row_sample_for_binding(row)
    lab_sample = normalize_lab_sample(sample)
    return lab_sample.normalized or sample


def _sample_identities(rows: list[dict[str, Any]]) -> set[str]:
    return {identity for row in rows if (identity := _sample_identity(row))}


async def rt_existing_import_summary(session: AsyncSession, rows: list[dict[str, Any]]) -> dict[str, Any]:
    identities = _sample_identities(rows)
    if not identities:
        return {"existing_rt_count": 0, "existing_rt_samples": [], "existing_object_ids": []}

    existing_samples: dict[str, dict[str, Any]] = {}
    object_ids: set[int] = set()

    rt_result = await session.execute(
        select(RtResult).where(
            or_(
                RtResult.normalized_sample_name.in_(identities),
                RtResult.sample_name_raw.in_(identities),
            )
        )
    )
    for result in rt_result.scalars().all():
        identity = normalize_lab_sample(result.normalized_sample_name or result.sample_name_raw).normalized
        if not identity:
            continue
        item = existing_samples.setdefault(
            identity,
            {"sample_identity": identity, "rt_results": 0, "stage_events": 0, "object_id": result.object_id},
        )
        item["rt_results"] += 1
        if result.object_id:
            item["object_id"] = result.object_id
            object_ids.add(result.object_id)

    event_result = await session.execute(
        select(StageEvent).where(
            StageEvent.stage_type == "realtime",
            StageEvent.source == "rt_import",
            or_(
                StageEvent.raw_json["normalized_sample_name"].as_string().in_(identities),
                StageEvent.raw_json["sample_name_raw"].as_string().in_(identities),
                StageEvent.raw_json["sample_object_no"].as_string().in_(identities),
            ),
        )
    )
    for event in event_result.scalars().all():
        identity = normalize_lab_sample(_event_sample_for_binding(event)).normalized
        if not identity:
            continue
        item = existing_samples.setdefault(
            identity,
            {"sample_identity": identity, "rt_results": 0, "stage_events": 0, "object_id": event.object_id},
        )
        item["stage_events"] += 1
        if event.object_id:
            item["object_id"] = event.object_id
            object_ids.add(event.object_id)

    return {
        "existing_rt_count": len(existing_samples),
        "existing_rt_samples": sorted(existing_samples.values(), key=lambda item: item["sample_identity"]),
        "existing_object_ids": sorted(object_ids),
    }


async def _delete_existing_rt_for_rows(session: AsyncSession, rows: list[dict[str, Any]]) -> dict[str, int]:
    identities = _sample_identities(rows)
    if not identities:
        return {"replaced_results": 0, "replaced_stage_events": 0}

    replaced_results = 0
    replaced_stage_events = 0
    affected_run_ids: set[int] = set()
    rt_result = await session.execute(
        select(RtResult).where(
            or_(
                RtResult.normalized_sample_name.in_(identities),
                RtResult.sample_name_raw.in_(identities),
            )
        )
    )
    for result in rt_result.scalars().all():
        affected_run_ids.add(result.rt_run_id)
        await session.delete(result)
        replaced_results += 1

    event_result = await session.execute(
        select(StageEvent).where(
            StageEvent.stage_type == "realtime",
            StageEvent.source == "rt_import",
            or_(
                StageEvent.raw_json["normalized_sample_name"].as_string().in_(identities),
                StageEvent.raw_json["sample_name_raw"].as_string().in_(identities),
                StageEvent.raw_json["sample_object_no"].as_string().in_(identities),
            ),
        )
    )
    for event in event_result.scalars().all():
        await session.delete(event)
        replaced_stage_events += 1

    await session.flush()
    for run_id in affected_run_ids:
        remaining = await session.scalar(select(func.count(RtResult.id)).where(RtResult.rt_run_id == run_id))
        if not remaining:
            run = await session.get(RtRun, run_id)
            if run:
                await session.delete(run)
    return {"replaced_results": replaced_results, "replaced_stage_events": replaced_stage_events}


async def import_rt_file(
    session: AsyncSession,
    path: str | Path,
    filename: str,
    file_sha256: str,
    user: User,
    *,
    quant_performer: str | None = None,
    employee_id: int | None = None,
    duplicate_mode: str = "block",
) -> tuple[RtRun, int, int, int, list[str], dict[str, int]]:
    preview = parse_rt_preview(path, source_filename=filename)
    aggregated = preview.aggregated_samples or []
    preview_rows, matched_count, unmatched_count = await rt_preview_rows_with_matches(session, aggregated)
    existing = await rt_existing_import_summary(session, preview_rows)
    if duplicate_mode == "block" and existing["existing_rt_count"]:
        samples = ", ".join(item["sample_identity"] for item in existing["existing_rt_samples"][:8])
        raise ValueError(f"RT-данные уже есть для образцов: {samples}. Выберите замену или новую попытку.")
    replaced = {"replaced_results": 0, "replaced_stage_events": 0}
    if duplicate_mode == "replace":
        await _delete_previous_rt_import(session, file_sha256)
        replaced = await _delete_existing_rt_for_rows(session, preview_rows)
    elif duplicate_mode not in {"block", "append"}:
        raise ValueError("Неизвестный режим повторного RT-импорта")
    performer_name = quant_performer
    if employee_id:
        employee = await session.get(Employee, employee_id)
        if employee:
            performer_name = employee.full_name
    run = RtRun(
        run_name=filename,
        run_date=datetime.combine(preview.run_date, time.min) if preview.run_date else None,
        instrument="QuantStudio/ABI" if preview.parser_type in {"abi_quantstudio", "abs_quant"} else None,
        quant_method=preview.quant_method,
        raw_json={
            "file_sha256": file_sha256,
            "parser_type": preview.parser_type,
            "source_filename": filename,
            "warnings": preview.warnings,
        },
    )
    session.add(run)
    await session.flush()
    for row in preview.rows:
        obj = await _resolve_sample_object(session, _row_sample_for_binding(row), user=user, create_repeat=True)
        session.add(RtResult(rt_run_id=run.id, object_id=obj.id if obj else None, **_rt_result_payload(row)))
    stage_events_written = 0
    for row in preview_rows:
        object_id = row.get("object_id")
        if not object_id:
            continue
        obj = await session.get(RegistryObject, object_id)
        if not obj:
            continue
        lab_sample = normalize_lab_sample(_row_sample_for_binding(row))
        if lab_sample.repeat_suffix:
            obj = await ensure_repeat_object(session, obj, lab_sample, user, source="rt_import")
        detail_data = {
            "quant_method": preview.quant_method,
            "quant_date": preview.run_date,
            "quant_performer": performer_name,
            "pipetting_method": "Ручной",
            "long_quantity": _round4(row.get("long_quantity")),
            "small_quantity": _round4(row.get("small_quantity")),
            "y_quantity": _round4(row.get("y_quantity")),
            "comment": None,
        }
        await create_stage_event(
            session,
            obj,
            stage_type="realtime",
            event_date=preview.run_date,
            source="rt_import",
            comment=None,
            raw_json={
                "source_file_sha256": file_sha256,
                "source_filename": filename,
                "rt_run_id": run.id,
                "sample_name_raw": row.get("sample_name_raw"),
                "normalized_sample_name": row.get("normalized_sample_name"),
                "sample_object_no": row.get("sample_object_no"),
                "repeat_suffix": row.get("repeat_suffix"),
                "targets": row.get("targets"),
            },
            created_by_user_id=user.id,
            detail_data=detail_data,
            performers=[{"employee_id": employee_id, "raw_name": performer_name, "role": "quant"}] if performer_name or employee_id else [],
        )
        stage_events_written += 1
    warnings = list(preview.warnings)
    if replaced["replaced_results"] or replaced["replaced_stage_events"]:
        warnings.append(
            f"Заменены старые RT-данные: результатов {replaced['replaced_results']}, событий {replaced['replaced_stage_events']}."
        )
    if unmatched_count:
        warnings.append(f"Не найдены объекты для образцов: {unmatched_count}")
    await write_audit(
        session,
        user,
        "rt_run",
        run.id,
        "import",
        None,
        {
            "filename": filename,
            "rows": len(preview.rows),
            "stage_events": stage_events_written,
            "duplicate_mode": duplicate_mode,
            **replaced,
        },
    )
    await session.commit()
    await session.refresh(run)
    return run, len(preview.rows), stage_events_written, unmatched_count, warnings, replaced


def _event_sample_for_binding(event: StageEvent) -> str | None:
    raw = event.raw_json or {}
    return raw.get("normalized_sample_name") or raw.get("sample_name_raw") or raw.get("sample_object_no")


async def repair_rt_repeat_objects(session: AsyncSession, user: User | None = None) -> dict[str, int]:
    objects_created_or_linked = 0
    rt_results_relinked = 0
    stage_events_relinked = 0
    affected_party_ids: set[int] = set()
    seen_repeat_numbers: set[str] = set()

    result = await session.execute(
        select(RtResult, RegistryObject)
        .join(RegistryObject, RegistryObject.id == RtResult.object_id)
        .where(or_(RtResult.normalized_sample_name.is_not(None), RtResult.sample_name_raw.is_not(None)))
    )
    for rt_result, obj in result.all():
        lab_sample = normalize_lab_sample(rt_result.normalized_sample_name or rt_result.sample_name_raw)
        if not lab_sample.repeat_suffix or not lab_sample.object_no:
            continue
        if obj.rcsme_reg_no == lab_sample.normalized and obj.repeat_suffix == lab_sample.repeat_suffix:
            continue
        if obj.rcsme_reg_no != lab_sample.object_no:
            continue
        repeat = await ensure_repeat_object(session, obj, lab_sample, user, source="rt_repair")
        if repeat.id != obj.id:
            rt_result.object_id = repeat.id
            rt_results_relinked += 1
            if repeat.party_id:
                affected_party_ids.add(repeat.party_id)
            if repeat.rcsme_reg_no:
                seen_repeat_numbers.add(repeat.rcsme_reg_no)

    event_result = await session.execute(
        select(StageEvent, RegistryObject)
        .join(RegistryObject, RegistryObject.id == StageEvent.object_id)
        .where(StageEvent.stage_type == "realtime", StageEvent.source == "rt_import")
    )
    for event, obj in event_result.all():
        lab_sample = normalize_lab_sample(_event_sample_for_binding(event))
        if not lab_sample.repeat_suffix or not lab_sample.object_no:
            continue
        if obj.rcsme_reg_no == lab_sample.normalized and obj.repeat_suffix == lab_sample.repeat_suffix:
            continue
        if obj.rcsme_reg_no != lab_sample.object_no:
            continue
        repeat = await ensure_repeat_object(session, obj, lab_sample, user, source="rt_repair")
        if repeat.id != obj.id:
            event.object_id = repeat.id
            stage_events_relinked += 1
            if repeat.party_id:
                affected_party_ids.add(repeat.party_id)
            if repeat.rcsme_reg_no:
                seen_repeat_numbers.add(repeat.rcsme_reg_no)

    if affected_party_ids:
        await recalculate_party_counts(session, affected_party_ids)
    if user:
        await write_audit(
            session,
            user,
            "rt_results",
            "bulk",
            "repair_rt_repeat_objects",
            None,
            {
                "repeat_objects": sorted(seen_repeat_numbers),
                "rt_results_relinked": rt_results_relinked,
                "stage_events_relinked": stage_events_relinked,
                "affected_party_ids": sorted(affected_party_ids),
            },
        )
    await session.commit()
    objects_created_or_linked = len(seen_repeat_numbers)
    return {
        "repeat_objects": objects_created_or_linked,
        "rt_results_relinked": rt_results_relinked,
        "stage_events_relinked": stage_events_relinked,
        "affected_parties": len(affected_party_ids),
    }


def _rt_result_payload(row: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "sample_name_raw",
        "normalized_sample_name",
        "sample_base",
        "well",
        "target",
        "ct",
        "cq",
        "quantity_ng_ul",
        "mean_quantity_ng_ul",
        "degradation_index",
        "ipc_ct",
        "result_flag",
        "raw_json",
    }
    return {key: value for key, value in row.items() if key in allowed}
