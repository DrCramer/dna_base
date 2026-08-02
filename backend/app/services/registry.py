from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import String, and_, delete, desc, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DnaExtraction,
    ElectrophoresisAnalysisEvent,
    ElectrophoresisEvent,
    ObjectPrepEvent,
    Party,
    PcrEvent,
    RegistryImportBatch,
    RegistryObject,
    RtResult,
    StageEvent,
    StageEventPerformer,
    User,
)
from app.parsers.normalization import extract_party_no, normalize_lab_sample, normalize_number, number_base
from app.services.case_year import infer_case_year
from app.parsers.registry import parse_registry
from app.services.audit import write_audit
from app.services.stages import delete_registry_stage_events, write_registry_stage_events


def _object_after(obj: RegistryObject) -> dict[str, Any]:
    return {
        "id": obj.id,
        "rcsme_reg_no": obj.rcsme_reg_no,
        "decree_no": obj.decree_no,
        "party_no": obj.party_no,
        "case_year": obj.case_year,
        "source_row_number": obj.source_row_number,
    }


STAGE_MODELS = {
    "object_prep_events": ObjectPrepEvent,
    "dna_extractions": DnaExtraction,
    "pcr_events": PcrEvent,
    "electrophoresis_events": ElectrophoresisEvent,
    "electrophoresis_analysis_events": ElectrophoresisAnalysisEvent,
}


def _object_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "stage_events"}


def _control_text(control: dict[str, Any], field: str) -> str | None:
    value = control.get(field)
    if isinstance(value, dict):
        text = value.get("text")
        return str(text) if text not in (None, "") else None
    return None


async def ensure_party(
    session: AsyncSession,
    party_no: str | None,
    filename: str,
    party_control: dict[str, Any],
    user: User,
    case_year: int | None = None,
) -> Party | None:
    if not party_no:
        return None
    result = await session.execute(select(Party).where(Party.party_no == party_no, Party.case_year == case_year))
    party = result.scalar_one_or_none()
    if not party:
        party = Party(
            party_no=party_no,
            case_year=case_year,
            title=party_no,
            status="active",
            created_by_user_id=user.id,
            object_count=0,
            raw_control_json={},
        )
        session.add(party)
        await session.flush()
    party.raw_control_json = {"filename": filename, **party_control}
    for field in (
        "control_actual_decrees",
        "control_decree_without_object",
        "control_object_without_decree",
        "control_unidentified_rostov_no",
        "control_need_recall",
        "control_recalled",
    ):
        value = _control_text(party_control, field)
        if value is not None:
            setattr(party, field, value)
    return party


async def recalculate_party_counts(session: AsyncSession, party_ids: set[int] | None = None) -> None:
    counts_stmt = select(RegistryObject.party_id, func.count(RegistryObject.id)).where(
        RegistryObject.party_id.is_not(None),
        RegistryObject.status != "archived",
    )
    if party_ids:
        counts_stmt = counts_stmt.where(RegistryObject.party_id.in_(party_ids))
    counts_stmt = counts_stmt.group_by(RegistryObject.party_id)
    counts = {party_id: int(count) for party_id, count in (await session.execute(counts_stmt)).all()}

    if party_ids:
        for party_id in party_ids:
            await session.execute(update(Party).where(Party.id == party_id).values(object_count=counts.get(party_id, 0)))
        return

    await session.execute(update(Party).values(object_count=0))
    for party_id, count in counts.items():
        await session.execute(update(Party).where(Party.id == party_id).values(object_count=count))


async def _generate_rcsme_reg_no(session: AsyncSession, decree_no: str | None, case_year: int | None = None) -> str | None:
    base = number_base(decree_no)
    if not base:
        return None
    result = await session.execute(
        select(RegistryObject.rcsme_reg_no).where(RegistryObject.rcsme_reg_no_base == base, RegistryObject.case_year == case_year)
    )
    suffixes: list[int] = []
    for value in result.scalars().all():
        normalized = normalize_number(value)
        if not normalized:
            continue
        parts = normalized.split("-", 1)
        if len(parts) != 2 or parts[0] != base:
            continue
        try:
            suffix = int(parts[1])
        except ValueError:
            continue
        if 0 < suffix < 1000:
            suffixes.append(suffix)
    next_suffix = (max(suffixes) + 1) if suffixes else 1
    return f"{base}-{next_suffix}"


async def _prepare_object_data(
    session: AsyncSession,
    object_data: dict[str, Any],
    existing: RegistryObject | None = None,
) -> dict[str, Any]:
    incoming_rcsme = object_data.get("rcsme_reg_no")
    if existing and existing.rcsme_reg_no_is_manual:
        object_data.pop("rcsme_reg_no", None)
        object_data.pop("rcsme_reg_no_base", None)
        return object_data
    if not incoming_rcsme and (not existing or not existing.rcsme_reg_no):
        generated = await _generate_rcsme_reg_no(session, object_data.get("decree_no"), object_data.get("case_year"))
        if generated:
            object_data["rcsme_reg_no"] = generated
            object_data["rcsme_reg_no_base"] = number_base(generated)
    return object_data


def registry_stage_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for event in row.get("stage_events", []):
            table = event.get("table")
            if table:
                counts[table] = counts.get(table, 0) + 1
    return counts



def _preview_case_year(rows: list[dict[str, Any]]) -> int:
    counts: dict[int, int] = {}
    for row in rows:
        year = infer_case_year(
            decision_date=row.get('decision_date'),
            decree_no=row.get('decree_no'),
            fallback=row.get('case_year'),
        )
        if year:
            counts[year] = counts.get(year, 0) + 1
    if counts:
        return sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)[0][0]
    return date.today().year


def registry_quality_warnings(rows: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    bad_analysis = 0
    for row in rows:
        for event in row.get("stage_events", []):
            if event.get("table") != "electrophoresis_analysis_events":
                continue
            data = event.get("data") or {}
            if not data.get("analysis_date"):
                bad_analysis += 1
    if bad_analysis:
        warnings.append(f"Пропущены некорректные строки анализа без даты: {bad_analysis}.")
    return warnings


async def existing_object_map(
    session: AsyncSession, rows: list[dict[str, Any]], case_year: int
) -> tuple[dict[str, RegistryObject], dict[str, RegistryObject]]:
    rcsme_values = []
    for row in rows:
        if not row.get("rcsme_reg_no"):
            continue
        rcsme_values.append(row["rcsme_reg_no"])
        normalized = normalize_lab_sample(row.get("rcsme_reg_no")).normalized
        if normalized and normalized != row["rcsme_reg_no"]:
            rcsme_values.append(normalized)
    decree_values = [row["decree_no"] for row in rows if row.get("decree_no")]
    by_rcsme: dict[str, RegistryObject] = {}
    by_decree: dict[str, RegistryObject] = {}
    if not rcsme_values and not decree_values:
        return by_rcsme, by_decree
    result = await session.execute(
        select(RegistryObject).where(
            or_(
                RegistryObject.decree_no.in_(decree_values),
                and_(RegistryObject.case_year == case_year, RegistryObject.rcsme_reg_no.in_(rcsme_values)),
            )
        )
    )
    for obj in result.scalars().all():
        if obj.rcsme_reg_no:
            by_rcsme[obj.rcsme_reg_no] = obj
            by_rcsme[normalize_number(obj.rcsme_reg_no) or obj.rcsme_reg_no] = obj
        if obj.decree_no:
            by_decree[obj.decree_no] = obj
    return by_rcsme, by_decree


async def _delete_registry_stage_events(session: AsyncSession, object_id: int, blocks: set[str]) -> int:
    deleted = 0
    for model in STAGE_MODELS.values():
        result = await session.execute(select(model).where(model.object_id == object_id))
        for item in result.scalars().all():
            raw = item.raw_json or {}
            if raw.get("source") == "registry_excel" and raw.get("block") in blocks:
                await session.delete(item)
                deleted += 1
    return deleted


async def _write_legacy_stage_events(
    session: AsyncSession,
    obj: RegistryObject,
    row: dict[str, Any],
    batch: RegistryImportBatch,
    file_sha256: str,
) -> int:
    events = row.get("stage_events", [])
    blocks = {event["block"] for event in events if event.get("block")}
    if not blocks:
        return 0
    deleted = await _delete_registry_stage_events(session, obj.id, blocks)
    if deleted:
        await session.flush()
    written = 0
    for event in events:
        model = STAGE_MODELS.get(event.get("table"))
        if model is None:
            continue
        raw_json = {
            **event.get("raw_json", {}),
            "source": "registry_excel",
            "block": event.get("block"),
            "source_import_batch_id": batch.id,
            "source_file_sha256": file_sha256,
            "source_row_number": row.get("source_row_number"),
            "source_sheet_name": row.get("source_sheet_name"),
        }
        session.add(model(object_id=obj.id, **event.get("data", {}), raw_json=raw_json))
        written += 1
    return written


async def find_registry_duplicates(
    session: AsyncSession,
    rows: list[dict[str, Any]],
    party_no: str | None = None,
    case_year: int | None = None,
) -> list[dict[str, Any]]:
    seen_rcsme: dict[str, int] = {}
    seen_decree: dict[str, int] = {}
    duplicates: list[dict[str, Any]] = []
    rcsme_values = [row["rcsme_reg_no"] for row in rows if row.get("rcsme_reg_no")]
    decree_values = [row["decree_no"] for row in rows if row.get("decree_no")]

    existing_rcsme: dict[str, dict[str, Any]] = {}
    existing_decree: dict[str, dict[str, Any]] = {}
    if rcsme_values or decree_values:
        result = await session.execute(
            select(RegistryObject.rcsme_reg_no, RegistryObject.decree_no, RegistryObject.party_no, Party.party_no)
            .outerjoin(Party, Party.id == RegistryObject.party_id)
            .where(
                or_(
                    RegistryObject.decree_no.in_(decree_values),
                    and_(RegistryObject.case_year == case_year, RegistryObject.rcsme_reg_no.in_(rcsme_values)),
                )
            )
        )
        for rcsme, decree, object_party_no, linked_party_no in result.all():
            existing = {"party_no": linked_party_no or object_party_no}
            if rcsme:
                existing_rcsme[rcsme] = existing
            if decree:
                existing_decree[decree] = existing

    def database_duplicate(row_no: int, field: str, value: str, existing: dict[str, Any]) -> dict[str, Any]:
        existing_party_no = existing.get("party_no")
        duplicate = {"row_number": row_no, "field": field, "value": value, "scope": "database"}
        if existing_party_no:
            duplicate["party_no"] = existing_party_no
        if party_no and existing_party_no and existing_party_no != party_no:
            duplicate["scope"] = "database_other_party"
            duplicate["current_party_no"] = existing_party_no
        return duplicate

    for row in rows:
        row_no = row["source_row_number"]
        rcsme = row.get("rcsme_reg_no")
        decree = row.get("decree_no")
        if rcsme in existing_rcsme:
            duplicates.append(database_duplicate(row_no, "rcsme_reg_no", rcsme, existing_rcsme[rcsme]))
        if decree in existing_decree:
            duplicates.append(database_duplicate(row_no, "decree_no", decree, existing_decree[decree]))
        if rcsme and rcsme in seen_rcsme:
            duplicates.append({"row_number": row_no, "field": "rcsme_reg_no", "value": rcsme, "scope": "file"})
        if decree and decree in seen_decree:
            duplicates.append({"row_number": row_no, "field": "decree_no", "value": decree, "scope": "file"})
        if rcsme:
            seen_rcsme[rcsme] = row_no
        if decree:
            seen_decree[decree] = row_no
    return duplicates


async def import_registry_file(
    session: AsyncSession,
    path: str | Path,
    filename: str,
    file_sha256: str,
    user: User,
    duplicate_mode: str = "block",
) -> tuple[RegistryImportBatch, list[str]]:
    preview = parse_registry(path)
    party_no = extract_party_no(filename)
    case_year = _preview_case_year(preview.rows)
    duplicates = await find_registry_duplicates(session, preview.rows, party_no=party_no, case_year=case_year)
    file_duplicate_keys = {(item["row_number"], item["field"]) for item in duplicates if item.get("scope") == "file"}
    warnings = [*preview.warnings, *registry_quality_warnings(preview.rows)]
    if file_duplicate_keys:
        warnings.append(f"Найдены дубликаты внутри файла: {len(file_duplicate_keys)}; такие строки пропущены.")
    database_duplicates = [item for item in duplicates if item.get("scope") == "database"]
    if duplicate_mode == "block" and database_duplicates:
        sample = ", ".join(
            f"{item.get('field')}={item.get('value')}" for item in database_duplicates[:8]
        )
        raise ValueError(
            "В реестре есть объекты, которые уже импортированы в эту партию. "
            f"Выберите режим «Заменить существующие данные» для повторного импорта. {sample}"
        )
    if duplicate_mode not in {"block", "replace"}:
        raise ValueError("Неизвестный режим повторного импорта реестра")
    if database_duplicates:
        stage_total = sum(registry_stage_counts(preview.rows).values())
        warnings.append(
            f"Будут заменены ранее импортированные данные этапов из этого реестра: "
            f"{len(database_duplicates)} совпадений объектов, {stage_total} stage-записей из файла."
        )
    cross_party_duplicates = [item for item in duplicates if item.get("scope") == "database_other_party"]
    if cross_party_duplicates:
        warnings.append(
            f"Найдены объекты из других партий: {len(cross_party_duplicates)}; они не будут перенесены в партию {party_no}."
        )
    existing_by_rcsme, existing_by_decree = await existing_object_map(session, preview.rows, case_year)
    party = await ensure_party(session, party_no, filename, preview.party_control, user, case_year=case_year)

    batch = RegistryImportBatch(
        original_filename=filename,
        party_no=party_no,
        file_sha256=file_sha256,
        stored_path=str(path),
        imported_by_user_id=user.id,
        rows_total=len(preview.rows),
        rows_imported=0,
        rows_skipped=len(preview.skipped_rows),
        import_log_json={
            "warnings": warnings,
            "duplicates": duplicates,
            "skipped_rows": preview.skipped_rows[:200],
            "party_control": preview.party_control,
            "stage_event_counts": registry_stage_counts(preview.rows),
        },
    )
    session.add(batch)
    await session.flush()

    imported = 0
    updated = 0
    stage_events_written = 0
    legacy_stage_events_written = 0
    skipped = len(preview.skipped_rows)
    for row in preview.rows:
        if (row["source_row_number"], "rcsme_reg_no") in file_duplicate_keys or (
            row["source_row_number"],
            "decree_no",
        ) in file_duplicate_keys:
            skipped += 1
            continue

        lab_sample = normalize_lab_sample(row.get("rcsme_reg_no"))
        is_repeat_row = bool(lab_sample.repeat_suffix)
        candidates = {
            existing_by_rcsme.get(row.get("rcsme_reg_no")),
            existing_by_rcsme.get(lab_sample.normalized),
        } if is_repeat_row else {
            obj
            for obj in (existing_by_rcsme.get(row.get("rcsme_reg_no")), existing_by_decree.get(row.get("decree_no")))
            if obj is not None
        }
        candidates = {obj for obj in candidates if obj is not None}
        if len(candidates) > 1:
            warnings.append(
                f"Строка {row['source_row_number']} пропущена: № рег РЦСМЭ и № постановления указывают на разные объекты."
            )
            skipped += 1
            continue
        if candidates and party:
            obj = next(iter(candidates))
            existing_party_no = obj.party_no
            if obj.party_id:
                existing_party = await session.get(Party, obj.party_id)
                existing_party_no = existing_party.party_no if existing_party else existing_party_no
            if (obj.party_id and obj.party_id != party.id) or (
                not obj.party_id and existing_party_no and party_no and existing_party_no != party_no
            ):
                warnings.append(
                    f"Строка {row['source_row_number']} пропущена: объект {obj.rcsme_reg_no or obj.decree_no} уже принадлежит партии {existing_party_no or obj.party_id}."
                )
                skipped += 1
                continue
        object_data = _object_fields(row)
        object_data['case_year'] = infer_case_year(decision_date=object_data.get('decision_date'), decree_no=object_data.get('decree_no'), fallback=case_year)
        if is_repeat_row:
            parent = None
            if party:
                parent_result = await session.execute(
                    select(RegistryObject).where(
                        RegistryObject.party_id == party.id,
                        RegistryObject.case_year == object_data.get("case_year"),
                        RegistryObject.rcsme_reg_no == lab_sample.object_no,
                    )
                )
                parent = parent_result.scalar_one_or_none()
            if parent:
                object_data["parent_object_id"] = parent.id
                object_data["repeat_suffix"] = lab_sample.repeat_suffix
                object_data["decree_no"] = None
                object_data["decree_no_base"] = None
            else:
                object_data["repeat_suffix"] = lab_sample.repeat_suffix
                warnings.append(
                    f"Строка {row['source_row_number']}: повтор {row.get('rcsme_reg_no')} импортирован без связи с оригиналом {lab_sample.object_no}."
                )
        object_data = await _prepare_object_data(session, object_data, next(iter(candidates), None))
        if candidates:
            obj = next(iter(candidates))
            for key, value in object_data.items():
                if value is not None:
                    setattr(obj, key, value)
            obj.party_no = party_no or obj.party_no
            obj.party_id = party.id if party else obj.party_id
            updated += 1
        else:
            obj = RegistryObject(
                **object_data,
                party_no=party_no,
                party_id=party.id if party else None,
                source_import_batch_id=batch.id,
            )
            session.add(obj)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                warnings.append(f"Строка {row['source_row_number']} пропущена из-за ограничения уникальности.")
                skipped += 1
                continue
            if obj.rcsme_reg_no:
                existing_by_rcsme[obj.rcsme_reg_no] = obj
            if obj.decree_no:
                existing_by_decree[obj.decree_no] = obj
            imported += 1
        await session.flush()
        legacy_stage_events_written += await _write_legacy_stage_events(session, obj, row, batch, file_sha256)
        stage_events_written += await write_registry_stage_events(session, obj, row, batch, file_sha256, user)
        await write_audit(session, user, "object", obj.id, "import", None, _object_after(obj))

    if party:
        await recalculate_party_counts(session, {party.id})

    batch.rows_imported = imported
    batch.rows_skipped = skipped
    batch.import_log_json = {
        **batch.import_log_json,
        "warnings": warnings,
        "objects_updated": updated,
        "stage_events_written": stage_events_written,
        "legacy_stage_events_written": legacy_stage_events_written,
    }
    await write_audit(session, user, "registry_import_batch", batch.id, "import", None, batch.import_log_json)
    await session.commit()
    await session.refresh(batch)
    return batch, warnings


async def search_objects(
    session: AsyncSession,
    q: str | None,
    party_no: str | None,
    status: str | None,
    limit: int | None,
    offset: int,
    case_year: int | None = None,
) -> tuple[list[RegistryObject], int]:
    stmt = select(RegistryObject)
    count_stmt = select(func.count(RegistryObject.id))
    conditions = []
    if q:
        query = q.strip()
        needle = f"%{query}%"
        stage_match = select(StageEvent.object_id).outerjoin(StageEventPerformer).where(
            or_(
                StageEvent.stage_type.ilike(needle),
                StageEvent.comment.ilike(needle),
                StageEvent.source.ilike(needle),
                StageEvent.raw_json.cast(String).ilike(needle),
                StageEventPerformer.raw_name.ilike(needle),
                StageEventPerformer.role.ilike(needle),
            )
        )
        rt_match = select(RtResult.object_id).where(
            or_(
                RtResult.sample_name_raw.ilike(needle),
                RtResult.normalized_sample_name.ilike(needle),
                RtResult.sample_base.ilike(needle),
                RtResult.target.ilike(needle),
                RtResult.result_flag.ilike(needle),
                RtResult.raw_json.cast(String).ilike(needle),
            )
        )
        party_match = select(Party.id).where(
            or_(Party.party_no.ilike(needle), Party.title.ilike(needle), Party.comment.ilike(needle))
        )
        conditions.append(
            or_(
                RegistryObject.rcsme_reg_no.ilike(needle),
                RegistryObject.party_no.ilike(needle),
                RegistryObject.decree_no.ilike(needle),
                RegistryObject.rcsme_reg_no_base.ilike(needle),
                RegistryObject.decree_no_base.ilike(needle),
                RegistryObject.external_military_no.ilike(needle),
                RegistryObject.object_description.ilike(needle),
                RegistryObject.investigator.ilike(needle),
                RegistryObject.object_type.ilike(needle),
                RegistryObject.box_no.ilike(needle),
                RegistryObject.party_id.in_(party_match),
                RegistryObject.id.in_(stage_match),
                RegistryObject.id.in_(rt_match),
            )
        )
    if party_no:
        conditions.append(RegistryObject.party_no == party_no.strip())
    if case_year is not None:
        conditions.append(RegistryObject.case_year == case_year)
    if status:
        conditions.append(RegistryObject.status == status)
    else:
        conditions.append(RegistryObject.status != "archived")
    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
    total = (await session.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(RegistryObject.id.desc()).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all()), total


async def delete_import_batch(session: AsyncSession, batch_id: int, user: User) -> bool:
    batch = await session.get(RegistryImportBatch, batch_id)
    if not batch:
        return False
    await session.execute(delete(RegistryObject).where(RegistryObject.source_import_batch_id == batch_id))
    await session.delete(batch)
    await write_audit(session, user, "registry_import_batch", batch_id, "delete", batch.import_log_json, None)
    await session.commit()
    return True


REPAIR_STAGE_TABLES = {"object_prep_events", "pcr_events", "electrophoresis_events", "electrophoresis_analysis_events"}
REPAIR_STAGE_TYPES = {"sample_prep", "pcr", "electrophoresis", "analysis"}


def _repair_row_stage_events(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [event for event in row.get("stage_events", []) if event.get("table") in REPAIR_STAGE_TABLES]


async def _objects_for_party(session: AsyncSession, party: Party) -> tuple[dict[str, RegistryObject], dict[str, RegistryObject]]:
    result = await session.execute(select(RegistryObject).where(RegistryObject.party_id == party.id))
    by_rcsme: dict[str, RegistryObject] = {}
    by_decree: dict[str, RegistryObject] = {}
    for obj in result.scalars().all():
        if obj.rcsme_reg_no:
            by_rcsme[obj.rcsme_reg_no] = obj
            normalized = normalize_number(obj.rcsme_reg_no)
            if normalized:
                by_rcsme[normalized] = obj
        if obj.decree_no:
            by_decree[obj.decree_no] = obj
    return by_rcsme, by_decree


async def _latest_repair_batches(
    session: AsyncSession,
    party_nos: set[str] | None,
) -> list[RegistryImportBatch]:
    stmt = (
        select(RegistryImportBatch)
        .join(Party, Party.party_no == RegistryImportBatch.party_no)
        .where(RegistryImportBatch.stored_path.is_not(None), Party.status == "active")
    )
    if party_nos:
        stmt = stmt.where(RegistryImportBatch.party_no.in_(party_nos))
    stmt = stmt.order_by(RegistryImportBatch.party_no, desc(RegistryImportBatch.imported_at), desc(RegistryImportBatch.id))
    result = await session.execute(stmt)
    latest: dict[str, RegistryImportBatch] = {}
    for batch in result.scalars().all():
        if not batch.party_no or batch.party_no in latest:
            continue
        if not batch.stored_path or not Path(batch.stored_path).exists():
            continue
        latest[batch.party_no] = batch
    return list(latest.values())


async def repair_registry_stage_events(
    session: AsyncSession,
    user: User | None = None,
    party_nos: list[str] | None = None,
) -> dict[str, Any]:
    requested = {str(value).strip() for value in party_nos or [] if str(value).strip()} or None
    batches = await _latest_repair_batches(session, requested)
    stats: dict[str, Any] = {
        "parties_seen": len(batches),
        "parties_repaired": 0,
        "objects_seen": 0,
        "objects_matched": 0,
        "events_deleted": 0,
        "events_written": 0,
        "skipped_rows": 0,
        "warnings": [],
        "parties": {},
    }
    affected_party_ids: set[int] = set()

    for batch in batches:
        if not batch.party_no or not batch.stored_path:
            continue
        party = (await session.execute(select(Party).where(Party.party_no == batch.party_no))).scalar_one_or_none()
        if not party:
            stats["warnings"].append(f"Партия {batch.party_no}: не найдена.")
            continue
        try:
            preview = parse_registry(batch.stored_path)
        except Exception as exc:  # pragma: no cover - surfaced in command output
            stats["warnings"].append(f"Партия {batch.party_no}: файл не прочитан ({exc}).")
            continue

        by_rcsme, by_decree = await _objects_for_party(session, party)
        party_stats = {
            "batch_id": batch.id,
            "filename": batch.original_filename,
            "rows": len(preview.rows),
            "objects_matched": 0,
            "events_deleted": 0,
            "events_written": 0,
            "skipped_rows": 0,
        }

        for row in preview.rows:
            stats["objects_seen"] += 1
            obj = None
            rcsme = row.get("rcsme_reg_no")
            decree = row.get("decree_no")
            if rcsme:
                obj = by_rcsme.get(rcsme) or by_rcsme.get(normalize_number(rcsme) or "")
            if obj is None and decree:
                obj = by_decree.get(decree)
            if obj is None:
                stats["skipped_rows"] += 1
                party_stats["skipped_rows"] += 1
                continue

            deleted = await delete_registry_stage_events(session, obj.id, set(), REPAIR_STAGE_TYPES)
            row_events = _repair_row_stage_events(row)
            written = 0
            if row_events:
                repair_row = {**row, "stage_events": row_events}
                written = await write_registry_stage_events(session, obj, repair_row, batch, batch.file_sha256, user)
            stats["objects_matched"] += 1
            stats["events_deleted"] += deleted
            stats["events_written"] += written
            party_stats["objects_matched"] += 1
            party_stats["events_deleted"] += deleted
            party_stats["events_written"] += written

        stats["parties_repaired"] += 1
        stats["parties"][batch.party_no] = party_stats
        affected_party_ids.add(party.id)

    if affected_party_ids:
        await recalculate_party_counts(session, affected_party_ids)
    await write_audit(session, user, "registry_import_batch", None, "repair_registry_stage_events", None, stats)
    await session.commit()
    return stats
