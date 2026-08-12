from datetime import date
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AnalysisDetail,
    DnaExtractionDetail,
    ElectrophoresisDetail,
    Employee,
    MillingDetail,
    PcrDetail,
    RealtimeDetail,
    RegistryImportBatch,
    RegistryObject,
    ReferenceItem,
    SamplePrepDetail,
    StageEvent,
    StageEventPerformer,
    User,
    WorkSession,
)
from app.parsers.normalization import clean_text


DETAIL_MODELS = {
    "sample_prep": SamplePrepDetail,
    "milling": MillingDetail,
    "dna_extraction": DnaExtractionDetail,
    "realtime": RealtimeDetail,
    "pcr": PcrDetail,
    "electrophoresis": ElectrophoresisDetail,
    "analysis": AnalysisDetail,
}

DETAIL_RELATIONSHIPS = {
    "sample_prep": "sample_prep_detail",
    "milling": "milling_detail",
    "dna_extraction": "dna_extraction_detail",
    "realtime": "realtime_detail",
    "pcr": "pcr_detail",
    "electrophoresis": "electrophoresis_detail",
    "analysis": "analysis_detail",
}

REFERENCE_FIELDS = {
    "dna_extraction": {"extraction_method": "extraction_method"},
    "realtime": {"quant_method": "quant_method", "pipetting_method": "pipetting_method"},
    "pcr": {"locus_panel": "pcr_panel", "pipetting_method": "pipetting_method"},
    "electrophoresis": {"sequencer": "sequencer", "pipetting_method": "pipetting_method"},
    "analysis": {"status": "analysis_status", "analysis_status": "analysis_status"},
}

ALLOWED_EMPLOYEE_ROLES = {"эксперт", "лаборант"}


def _looks_like_person_name(value: str | None) -> bool:
    name = clean_text(value)
    if not name:
        return False
    if any(char.isdigit() for char in name):
        return False
    if len(name) > 80:
        return False
    parts = re.split(r"\s+", name)
    if len(parts) < 2:
        return False
    return bool(re.search(r"[А-ЯЁA-Z][а-яёa-z-]+\s+[А-ЯЁA-Z]\.?(?:\s*[А-ЯЁA-Z]\.?)?", name))


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [text for item in value if (text := clean_text(item))]
    text = clean_text(value)
    return [text] if text else []


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return ", ".join([text for item in value if (text := clean_text(item))]) or None
    return clean_text(value)


def _initials(name: str) -> str | None:
    parts = [part for part in re.split(r"\s+", name.strip()) if part]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {' '.join(part[:1] + '.' for part in parts[1:] if part)}"


async def ensure_employee(session: AsyncSession, raw_name: str | None, role: str) -> Employee | None:
    name = clean_text(raw_name)
    if not name:
        return None
    result = await session.execute(select(Employee).where(Employee.full_name == name))
    employee = result.scalar_one_or_none()
    if employee:
        return employee
    if not _looks_like_person_name(name):
        return None
    employee = Employee(
        full_name=name,
        short_name=name,
        initials=_initials(name),
        role=role if role in ALLOWED_EMPLOYEE_ROLES else None,
        is_verified=False,
        is_active=False,
    )
    session.add(employee)
    await session.flush()
    return employee


async def ensure_reference_item(session: AsyncSession, category: str, raw_name: Any) -> ReferenceItem | None:
    name = clean_text(raw_name)
    if not name:
        return None
    result = await session.execute(
        select(ReferenceItem).where(ReferenceItem.category == category, ReferenceItem.name == name)
    )
    item = result.scalar_one_or_none()
    if item:
        return item
    item = ReferenceItem(category=category, name=name, short_name=None, comment="импортировано из Excel", is_active=True)
    session.add(item)
    await session.flush()
    return item


async def ensure_reference_items_for_stage(session: AsyncSession, stage_type: str, data: dict[str, Any]) -> None:
    for field, category in REFERENCE_FIELDS.get(stage_type, {}).items():
        await ensure_reference_item(session, category, data.get(field))


async def next_attempt_no(session: AsyncSession, object_id: int, stage_type: str) -> int:
    result = await session.execute(
        select(func.coalesce(func.max(StageEvent.attempt_no), 0) + 1).where(
            StageEvent.object_id == object_id,
            StageEvent.stage_type == stage_type,
            StageEvent.is_cancelled.is_(False),
        )
    )
    return int(result.scalar_one())


def _detail_payload(stage_type: str, data: dict[str, Any]) -> dict[str, Any]:
    if stage_type == "sample_prep":
        return {
            "registry_filled_by": data.get("registry_filled_by"),
            "photo_performers": _as_list(data.get("photo_performers")),
            "photo_assistants": _as_list(data.get("photo_assistants")),
            "washing_performers": _as_list(data.get("washing_performers")),
            "washing_assistants": _as_list(data.get("washing_assistants")),
            "washing_date": data.get("washing_date"),
            "bone_tissue_performers": _as_list(data.get("bone_tissue_performers")),
            "bone_tissue_date": data.get("bone_tissue_date"),
        }
    if stage_type == "milling":
        return {
            "milling_performers": _as_list(data.get("milling_performers")),
            "cups": _as_text(data.get("cups")),
            "milling_date": data.get("milling_date"),
        }
    if stage_type == "dna_extraction":
        return {
            "extraction_date": data.get("extraction_date"),
            "extraction_method": data.get("extraction_method"),
        }
    if stage_type == "realtime":
        return {
            "quant_method": data.get("quant_method"),
            "quant_date": data.get("quant_date"),
            "quant_performer": data.get("quant_performer"),
            "pipetting_method": data.get("pipetting_method"),
            "concentration": data.get("concentration"),
            "ct_cq": data.get("ct_cq"),
            "di": data.get("di"),
            "ipc": data.get("ipc"),
            "long_quantity": data.get("long_quantity"),
            "small_quantity": data.get("small_quantity"),
            "y_quantity": data.get("y_quantity"),
            "comment": data.get("comment"),
        }
    if stage_type == "pcr":
        return {
            "pcr_date": data.get("pcr_date"),
            "locus_panel": data.get("locus_panel"),
            "pipetting_method": data.get("pipetting_method"),
            "normalization_performers": _as_list(data.get("normalization_performers")),
            "pcr_performers": _as_list(data.get("pcr_performers")),
        }
    if stage_type == "electrophoresis":
        return {
            "electrophoresis_date": data.get("electrophoresis_date"),
            "sequencer": data.get("sequencer"),
            "pipetting_method": data.get("pipetting_method"),
            "performers": _as_list(data.get("performers")),
        }
    if stage_type == "analysis":
        return {
            "genotype": data.get("genotype"),
            "analysis_date": data.get("analysis_date"),
            "status": data.get("status"),
        }
    return {}


async def create_stage_event(
    session: AsyncSession,
    obj: RegistryObject,
    *,
    stage_type: str,
    event_date: date | None = None,
    source: str = "manual",
    comment: str | None = None,
    raw_json: dict[str, Any] | None = None,
    created_by_user_id: int | None = None,
    work_session: WorkSession | None = None,
    attempt_no: int | None = None,
    detail_data: dict[str, Any] | None = None,
    performers: list[dict[str, Any]] | None = None,
) -> StageEvent:
    event = StageEvent(
        object_id=obj.id,
        work_session_id=work_session.id if work_session else None,
        stage_type=stage_type,
        attempt_no=attempt_no or await next_attempt_no(session, obj.id, stage_type),
        event_date=event_date,
        source=source,
        comment=comment,
        raw_json=raw_json or {},
        created_by_user_id=created_by_user_id,
        is_cancelled=False,
    )
    session.add(event)
    await session.flush()

    for index, performer in enumerate(performers or []):
        raw_name = clean_text(performer.get("raw_name"))
        role = clean_text(performer.get("role")) or "performer"
        employee_id = performer.get("employee_id")
        if not employee_id:
            employee = await ensure_employee(session, raw_name, role)
            employee_id = employee.id if employee else None
        session.add(
            StageEventPerformer(
                stage_event_id=event.id,
                employee_id=employee_id,
                role=role,
                order_index=index,
                raw_name=raw_name,
            )
        )

    detail_model = DETAIL_MODELS.get(stage_type)
    if detail_model:
        detail_input = dict(detail_data or {})
        if stage_type == "realtime" and source != "rt_import":
            for key in ("long_quantity", "small_quantity", "y_quantity"):
                detail_input.pop(key, None)
        payload = _detail_payload(stage_type, detail_input)
        await ensure_reference_items_for_stage(session, stage_type, payload)
        session.add(detail_model(stage_event_id=event.id, **payload))
    return event


async def update_stage_event_data(
    session: AsyncSession,
    event: StageEvent,
    *,
    stage_type: str,
    event_date: date | None = None,
    comment: str | None = None,
    comment_touched: bool = False,
    raw_json: dict[str, Any] | None = None,
    detail_data: dict[str, Any] | None = None,
    performers: list[dict[str, Any]] | None = None,
    performers_touched: bool = False,
) -> StageEvent:
    if event_date is not None:
        event.event_date = event_date
    if comment_touched:
        event.comment = comment
    if raw_json is not None:
        event.raw_json = {**(event.raw_json or {}), **raw_json}

    detail_model = DETAIL_MODELS.get(stage_type)
    relationship_name = DETAIL_RELATIONSHIPS.get(stage_type)
    if detail_model and relationship_name:
        detail_input = dict(detail_data or {})
        if stage_type == "realtime" and event.source != "rt_import":
            for key in ("long_quantity", "small_quantity", "y_quantity"):
                detail_input.pop(key, None)
        payload = _detail_payload(stage_type, detail_input)
        await ensure_reference_items_for_stage(session, stage_type, payload)
        detail = getattr(event, relationship_name, None)
        if detail is None:
            session.add(detail_model(stage_event_id=event.id, **payload))
        else:
            for key, value in payload.items():
                setattr(detail, key, value)

    if performers_touched:
        for performer in list(event.performers or []):
            await session.delete(performer)
        await session.flush()
        for index, performer in enumerate(performers or []):
            raw_name = clean_text(performer.get("raw_name"))
            role = clean_text(performer.get("role")) or "performer"
            employee_id = performer.get("employee_id")
            if not employee_id:
                employee = await ensure_employee(session, raw_name, role)
                employee_id = employee.id if employee else None
            session.add(
                StageEventPerformer(
                    stage_event_id=event.id,
                    employee_id=employee_id,
                    role=role,
                    order_index=index,
                    raw_name=raw_name,
                )
            )
    return event


def _registry_common_raw(
    source_raw: dict[str, Any],
    event: dict[str, Any],
    row: dict[str, Any],
    batch: RegistryImportBatch,
    file_sha256: str,
) -> dict[str, Any]:
    return {
        **source_raw,
        "source": "registry_excel",
        "block": event.get("block"),
        "legacy_table": event.get("table"),
        "source_import_batch_id": batch.id,
        "source_file_sha256": file_sha256,
        "source_row_number": row.get("source_row_number"),
        "source_sheet_name": row.get("source_sheet_name"),
    }


def _cups_from_comment(value: str | None) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    match = re.search(r"стакан(?:ы|ов)?\s*:\s*(.+)$", text, flags=re.IGNORECASE)
    return clean_text(match.group(1)) if match else None


def _comment_without_cups(value: str | None) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    return None if re.search(r"стакан(?:ы|ов)?\s*:", text, flags=re.IGNORECASE) else text


def _latest_date(*values: date | None) -> date | None:
    dates = [value for value in values if value is not None]
    return max(dates) if dates else None


def _merge_unique(*values: Any) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in _as_list(value):
            if item not in seen:
                seen.add(item)
                merged.append(item)
    return merged


def _merge_comments(*values: str | None) -> str | None:
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(value)
        if text and text not in seen:
            seen.add(text)
            items.append(text)
    return "; ".join(items) if items else None


def _merge_sample_prep_specs(items: list[dict[str, Any]], registry_filled_by: Any = None) -> dict[str, Any] | None:
    row_registry_filled_by = clean_text(registry_filled_by)
    if not items and not row_registry_filled_by:
        return None
    details = [item.get("detail_data") or {} for item in items]
    performers = []
    for item in items:
        performers.extend(item.get("performers") or [])
    filled_by = next((detail.get("registry_filled_by") for detail in details if detail.get("registry_filled_by")), None)
    filled_by = filled_by or row_registry_filled_by
    return {
        "stage_type": "sample_prep",
        "event_date": _latest_date(*(item.get("event_date") for item in items)),
        "comment": _merge_comments(*(item.get("comment") for item in items)),
        "attempt_no": None,
        "detail_data": {
            "registry_filled_by": filled_by,
            "photo_performers": _merge_unique(*(detail.get("photo_performers") for detail in details)),
            "photo_assistants": _merge_unique(*(detail.get("photo_assistants") for detail in details)),
            "washing_performers": _merge_unique(*(detail.get("washing_performers") for detail in details)),
            "washing_assistants": _merge_unique(*(detail.get("washing_assistants") for detail in details)),
            "washing_date": _latest_date(*(detail.get("washing_date") for detail in details)),
            "bone_tissue_performers": _merge_unique(*(detail.get("bone_tissue_performers") for detail in details)),
            "bone_tissue_date": _latest_date(*(detail.get("bone_tissue_date") for detail in details)),
        },
        "performers": performers,
    }


def registry_event_specs(event: dict[str, Any]) -> list[dict[str, Any]]:
    table = event.get("table")
    data = event.get("data") or {}
    specs: list[dict[str, Any]] = []

    if table == "object_prep_events":
        legacy_stage = data.get("stage_type")
        if legacy_stage == "mill_grinding":
            cups = _cups_from_comment(data.get("comment"))
            specs.append(
                {
                    "stage_type": "milling",
                    "event_date": data.get("event_date"),
                    "comment": _comment_without_cups(data.get("comment")),
                    "attempt_no": None,
                    "detail_data": {
                        "milling_performers": _as_list(data.get("performer")),
                        "cups": cups,
                        "milling_date": data.get("event_date"),
                    },
                    "performers": [{"raw_name": data.get("performer"), "role": "performer"}],
                }
            )
        else:
            detail_data: dict[str, Any] = {"registry_filled_by": None}
            performers: list[dict[str, Any]] = []
            if legacy_stage == "photo":
                detail_data["photo_performers"] = _as_list(data.get("performer"))
                detail_data["photo_assistants"] = _as_list(data.get("assistant"))
                performers = [
                    {"raw_name": data.get("performer"), "role": "photo"},
                    {"raw_name": data.get("assistant"), "role": "assistant"},
                ]
            elif legacy_stage == "washing":
                detail_data["washing_performers"] = _as_list(data.get("performer"))
                detail_data["washing_assistants"] = _as_list(data.get("assistant"))
                detail_data["washing_date"] = data.get("event_date")
                performers = [
                    {"raw_name": data.get("performer"), "role": "washing"},
                    {"raw_name": data.get("assistant"), "role": "assistant"},
                ]
            else:
                detail_data["bone_tissue_performers"] = _as_list(data.get("performer"))
                detail_data["bone_tissue_date"] = data.get("event_date")
                performers = [{"raw_name": data.get("performer"), "role": "performer"}]
            specs.append(
                {
                    "stage_type": "sample_prep",
                    "event_date": data.get("event_date"),
                    "comment": data.get("comment"),
                    "attempt_no": None,
                    "detail_data": detail_data,
                    "performers": performers,
                }
            )
        return specs

    if table == "dna_extractions":
        extraction_no = data.get("extraction_no") or None
        extraction_comment = data.get("extraction_comment") if "extraction_comment" in data else data.get("comment")
        quant_comment = data.get("quant_comment") if "quant_comment" in data else data.get("comment")
        if any(data.get(key) for key in ("extraction_date", "performer", "extraction_method")) or extraction_comment:
            specs.append(
                {
                    "stage_type": "dna_extraction",
                    "event_date": data.get("extraction_date"),
                    "comment": extraction_comment,
                    "attempt_no": extraction_no,
                    "detail_data": data,
                    "performers": [{"raw_name": data.get("performer"), "role": "dna_extraction"}],
                }
            )
        if any(data.get(key) for key in ("quant_method", "quant_date", "quant_performer", "pipetting_method")) or quant_comment:
            specs.append(
                {
                    "stage_type": "realtime",
                    "event_date": data.get("quant_date"),
                    "comment": quant_comment,
                    "attempt_no": extraction_no,
                    "detail_data": data,
                    "performers": [{"raw_name": data.get("quant_performer"), "role": "quant"}],
                }
            )
        return specs

    if table == "pcr_events":
        return [
            {
                "stage_type": "pcr",
                "event_date": data.get("pcr_date"),
                "comment": data.get("comment"),
                "attempt_no": None,
                "detail_data": {
                    **data,
                    "normalization_performers": _as_list(data.get("normalization_performer")),
                    "pcr_performers": _as_list(data.get("pcr_performer")),
                },
                "performers": [
                    {"raw_name": data.get("normalization_performer"), "role": "normalization"},
                    {"raw_name": data.get("pcr_performer"), "role": "pcr"},
                ],
            }
        ]

    if table == "electrophoresis_events":
        return [
            {
                "stage_type": "electrophoresis",
                "event_date": data.get("electrophoresis_date"),
                "comment": data.get("comment"),
                "attempt_no": None,
                "detail_data": {
                    **data,
                    "performers": _as_list(data.get("performer_1")) + _as_list(data.get("performer_2")),
                },
                "performers": [
                    {"raw_name": data.get("performer_1"), "role": "performer"},
                    {"raw_name": data.get("performer_2"), "role": "performer"},
                ],
            }
        ]

    if table == "electrophoresis_analysis_events":
        return [
            {
                "stage_type": "analysis",
                "event_date": data.get("analysis_date"),
                "comment": data.get("comment"),
                "attempt_no": data.get("attempt_no") or None,
                "detail_data": {
                    "genotype": data.get("genotype"),
                    "analysis_date": data.get("analysis_date"),
                    "status": data.get("result_status"),
                },
                "performers": [{"raw_name": data.get("performer"), "role": "analysis"}],
            }
        ]

    return []


async def delete_registry_stage_events(
    session: AsyncSession,
    object_id: int,
    blocks: set[str],
    stage_types: set[str],
) -> int:
    if not blocks and not stage_types:
        return 0
    result = await session.execute(
        select(StageEvent).where(
            StageEvent.object_id == object_id,
            StageEvent.source == "registry_excel",
        )
    )
    deleted = 0
    for event in result.scalars().all():
        raw = event.raw_json or {}
        source_blocks = set(raw.get("source_blocks") or [])
        raw_stage_type = raw.get("canonical_stage_type")
        block_matches = raw.get("block") in blocks or bool(source_blocks.intersection(blocks))
        stage_matches = event.stage_type in stage_types or raw_stage_type in stage_types
        if not block_matches and not stage_matches:
            continue
        await session.delete(event)
        deleted += 1
    return deleted


async def write_registry_stage_events(
    session: AsyncSession,
    obj: RegistryObject,
    row: dict[str, Any],
    batch: RegistryImportBatch,
    file_sha256: str,
    user: User | None,
) -> int:
    events = row.get("stage_events", [])
    blocks = {event["block"] for event in events if event.get("block")}
    written = 0
    sample_prep_specs: list[dict[str, Any]] = []
    deferred_specs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for event in events:
        for spec in registry_event_specs(event):
            if spec["stage_type"] == "sample_prep":
                sample_prep_specs.append(spec)
            else:
                deferred_specs.append((event, spec))

    stage_types = {spec["stage_type"] for spec in sample_prep_specs}
    if clean_text(row.get("registry_filled_by")):
        stage_types.add("sample_prep")
    stage_types.update(spec["stage_type"] for _, spec in deferred_specs)
    deleted = await delete_registry_stage_events(session, obj.id, blocks, stage_types)
    if deleted:
        await session.flush()

    merged_sample_prep = _merge_sample_prep_specs(sample_prep_specs, row.get("registry_filled_by"))
    if merged_sample_prep:
        source_raw = {}
        for event in events:
            if event.get("table") == "object_prep_events":
                source_raw.update(event.get("raw_json", {}))
        raw_json = _registry_common_raw(source_raw, {"block": "sample_prep", "table": "object_prep_events"}, row, batch, file_sha256)
        raw_json["canonical_stage_type"] = "sample_prep"
        raw_json["source_blocks"] = sorted(blocks)
        await create_stage_event(
            session,
            obj,
            stage_type="sample_prep",
            event_date=merged_sample_prep.get("event_date"),
            source="registry_excel",
            comment=merged_sample_prep.get("comment"),
            raw_json=raw_json,
            created_by_user_id=user.id if user else None,
            attempt_no=merged_sample_prep.get("attempt_no"),
            detail_data=merged_sample_prep.get("detail_data"),
            performers=merged_sample_prep.get("performers"),
        )
        written += 1

    for event, spec in deferred_specs:
        raw_json = _registry_common_raw(event.get("raw_json", {}), event, row, batch, file_sha256)
        raw_json["canonical_stage_type"] = spec["stage_type"]
        await create_stage_event(
            session,
            obj,
            stage_type=spec["stage_type"],
            event_date=spec.get("event_date"),
            source="registry_excel",
            comment=spec.get("comment"),
            raw_json=raw_json,
            created_by_user_id=user.id if user else None,
            attempt_no=spec.get("attempt_no"),
            detail_data=spec.get("detail_data"),
            performers=spec.get("performers"),
        )
        written += 1
    return written


async def stage_summary_for_objects(session: AsyncSession, object_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not object_ids:
        return {}
    result = await session.execute(
        select(
            StageEvent.object_id,
            StageEvent.stage_type,
            func.count(StageEvent.id),
            func.max(StageEvent.event_date),
        )
        .where(StageEvent.object_id.in_(object_ids), StageEvent.is_cancelled.is_(False))
        .group_by(StageEvent.object_id, StageEvent.stage_type)
    )
    summaries: dict[int, dict[str, Any]] = {}
    for object_id, stage_type, count, latest_date in result.all():
        summary = summaries.setdefault(object_id, {"stage_summary": {}, "repeat_count": 0})
        summary["stage_summary"][stage_type] = {"count": int(count), "latest_date": latest_date}
        if count and int(count) > 1:
            summary["repeat_count"] += int(count) - 1

    latest_result = await session.execute(
        select(StageEvent)
        .where(StageEvent.object_id.in_(object_ids), StageEvent.is_cancelled.is_(False))
        .order_by(StageEvent.object_id, StageEvent.event_date.desc().nullslast(), StageEvent.id.desc())
    )
    seen: set[int] = set()
    for event in latest_result.scalars().all():
        if event.object_id in seen:
            continue
        seen.add(event.object_id)
        summary = summaries.setdefault(event.object_id, {"stage_summary": {}, "repeat_count": 0})
        summary["last_stage"] = event.stage_type
        summary["last_stage_date"] = event.event_date
    return summaries
