from pathlib import Path
import hashlib
import re
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, db_session, edit_user
from app.models import ElectrophoresisControlFile, ElectrophoresisResultFile, Employee, Party, RegistryObject, StageEvent, User
from app.parsers.normalization import clean_text, extract_lab_samples_from_text, extract_party_no, normalize_number, number_base
from app.parsers.registration_list import RegistrationListColumn, parse_registration_list
from app.parsers.registry import parse_registry
from app.parsers.rt import parse_rt_preview
from app.parsers.work_protocol import parse_work_protocol_preview
from app.schemas import (
    ElectrophoresisPdfCommitRequest,
    ElectrophoresisPdfCommitResponse,
    ElectrophoresisPdfPreviewItem,
    ElectrophoresisPdfPreviewResponse,
    ImportCommitRequest,
    ImportCommitResponse,
    ImportPreviewResponse,
    RcsmeFixApplyResponse,
    RcsmeFixPreviewItem,
    RcsmeFixPreviewResponse,
    RegistrationBulkRow,
    RegistrationListCommitRequest,
    RegistrationListCommitResponse,
    RegistrationListPartyPreview,
    RegistrationListPreviewOut,
    RtCommitRequest,
    RtCommitResponse,
    RtPreviewResponse,
    WorkProtocolPreviewResponse,
)
from app.services.files import save_upload, upload_metadata, upload_path
from app.services.registry import (
    delete_import_batch,
    existing_object_map,
    find_registry_duplicates,
    import_registry_file,
    registry_quality_warnings,
    registry_stage_counts,
    _preview_case_year,
    recalculate_party_counts,
)
from app.services.audit import write_audit
from app.services.repeats import ensure_repeat_object
from app.services.rt import import_rt_file, rt_existing_import_summary, rt_preview_rows_with_matches
from app.services.stages import create_stage_event


router = APIRouter(prefix="/imports", tags=["imports"])


def _compact_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _parse_positive_int(value: str, field_name: str) -> int:
    text = _compact_text(value)
    if not text or not text.isdigit():
        raise HTTPException(status_code=400, detail=f"{field_name} должен быть числом")
    return int(text)


def _parse_rcsme_start(value: str) -> tuple[int, int]:
    normalized = normalize_number(value)
    if not normalized:
        raise HTTPException(status_code=400, detail="Не удалось определить начальный № рег РЦСМЭ")
    if "-" in normalized:
        base_text, suffix_text = normalized.split("-", 1)
    else:
        base_text, suffix_text = normalized, "1"
    if not base_text.isdigit() or not suffix_text.isdigit():
        raise HTTPException(status_code=400, detail="Начальный № рег РЦСМЭ должен быть в формате 100-1")
    return int(base_text), int(suffix_text)


def _object_sort_key(obj: RegistryObject) -> tuple[int, str, int]:
    base = obj.rcsme_reg_no_base or number_base(obj.rcsme_reg_no)
    numeric = int(base) if base and str(base).isdigit() else 10**12
    return numeric, obj.rcsme_reg_no or "", obj.id


async def _registration_list_start_hint(session: AsyncSession, case_year: int) -> tuple[str, str | None, str | None]:
    rows = (
        await session.execute(
            select(RegistryObject.rcsme_reg_no, RegistryObject.rcsme_reg_no_base, Party.party_no)
            .join(Party, Party.id == RegistryObject.party_id, isouter=True)
            .where(RegistryObject.status != "archived", RegistryObject.case_year == case_year)
        )
    ).all()
    best: tuple[int, str | None, str | None] | None = None
    for rcsme_reg_no, rcsme_reg_no_base, party_no in rows:
        base = rcsme_reg_no_base or number_base(rcsme_reg_no)
        if not base or not str(base).isdigit():
            continue
        numeric = int(base)
        if best is None or numeric > best[0]:
            best = (numeric, party_no, rcsme_reg_no or f"{numeric}-1")
    if best is None:
        return "1-1", None, None
    return f"{best[0] + 1}-1", best[1], best[2]


async def _registration_party_objects(session: AsyncSession, party_id: int) -> list[RegistryObject]:
    result = await session.execute(
        select(RegistryObject).where(RegistryObject.party_id == party_id, RegistryObject.status != "archived")
    )
    return sorted(result.scalars().all(), key=_object_sort_key)


async def _registration_list_existing_parties(
    session: AsyncSession,
    party_nos: list[str],
    case_year: int,
) -> dict[str, tuple[Party, list[RegistryObject]]]:
    if not party_nos:
        return {}
    parties_result = await session.execute(
        select(Party).where(Party.case_year == case_year, Party.party_no.in_(party_nos))
    )
    parties = {party.party_no: party for party in parties_result.scalars().all()}
    objects_by_party: dict[str, list[RegistryObject]] = {}
    if parties:
        objects_result = await session.execute(
            select(RegistryObject).where(
                RegistryObject.party_id.in_([party.id for party in parties.values()]),
                RegistryObject.status != "archived",
            )
        )
        for obj in objects_result.scalars().all():
            objects_by_party.setdefault(obj.party_no or "", []).append(obj)
    return {
        party_no: (party, sorted(objects_by_party.get(party_no, []), key=_object_sort_key))
        for party_no, party in parties.items()
    }


def _registration_list_party_no(start_party_no: int, offset: int) -> str:
    return str(start_party_no + offset)


def _registration_list_new_row(
    *,
    index: int,
    registry_row_no: str,
    rcsme_base: int,
    rcsme_suffix: int,
    case_year: int,
    external_military_no: str | None,
    intake_date: date | None,
    decision_date: date | None,
    investigator: str | None,
    incoming_no: str | None,
    box_no: str | None,
    conflicts: list[str] | None = None,
) -> RegistrationBulkRow:
    return RegistrationBulkRow(
        index=index,
        registry_row_no=registry_row_no,
        rcsme_reg_no=f"{rcsme_base}-{rcsme_suffix}",
        decree_no=f"{rcsme_base}-{case_year}",
        external_military_no=external_military_no,
        intake_date=intake_date,
        decision_date=decision_date,
        investigator=_compact_text(investigator),
        incoming_no=_compact_text(incoming_no),
        box_no=_compact_text(box_no),
        conflicts=conflicts or [],
    )


async def _build_registration_list_preview(
    session: AsyncSession,
    path: Path,
    *,
    upload_id: str,
    filename: str,
    file_sha256: str,
    start_party_no: str,
    case_year: int,
    intake_date: date | None,
    decision_date: date | None,
    investigator: str | None,
    incoming_no: str | None,
    box_no: str | None,
    duplicate_mode: str = "block",
) -> tuple[RegistrationListPreviewOut, list[RegistrationListColumn]]:
    start_party_numeric = _parse_positive_int(start_party_no, "Стартовая партия")
    if case_year < 1900 or case_year > 2200:
        raise HTTPException(status_code=400, detail="Год должен быть в диапазоне 1900–2200")
    parsed = parse_registration_list(path)
    suggested_start, previous_party_no, previous_last = await _registration_list_start_hint(session, case_year)
    start_base, rcsme_suffix = _parse_rcsme_start(suggested_start)
    party_nos = [_registration_list_party_no(start_party_numeric, index) for index, _ in enumerate(parsed.columns)]
    existing = await _registration_list_existing_parties(session, party_nos, case_year)

    parties: list[RegistrationListPartyPreview] = []
    conflicts: list[str] = []
    warnings = list(parsed.warnings)
    next_base = start_base
    generated_rows: list[tuple[str, RegistrationBulkRow]] = []

    for column_index, column in enumerate(parsed.columns):
        party_no = party_nos[column_index]
        existing_party, existing_objects = existing.get(party_no, (None, []))
        existing_count = len(existing_objects)
        party_warnings: list[str] = []
        status = "будет создана"
        will_create_party = existing_party is None

        if existing_party and existing_count and duplicate_mode == "block":
            status = "нужна замена"
            message = f"Партия {party_no} за {case_year} уже содержит {existing_count} объект(ов)"
            conflicts.append(message)
            party_warnings.append(message)
        elif existing_party and existing_count:
            status = "будет обновлена"
            party_warnings.append(f"Будут обновлены первые {min(existing_count, len(column.values))} объект(ов).")
            if existing_count > len(column.values):
                party_warnings.append(f"В партии останутся без изменений лишние объекты: {existing_count - len(column.values)}.")
            if len(column.values) > existing_count:
                party_warnings.append(f"Будет создано новых объектов: {len(column.values) - existing_count}.")
        elif existing_party:
            status = "существует пустая"
            party_warnings.append("Партия уже есть, но активных объектов в ней нет.")

        sample_rows: list[RegistrationBulkRow] = []
        first_rcsme: str | None = None
        last_rcsme: str | None = None
        for row_index, external_no in enumerate(column.values):
            if existing_party and duplicate_mode != "block" and row_index < existing_count:
                obj = existing_objects[row_index]
                row = RegistrationBulkRow(
                    index=row_index + 1,
                    object_id=obj.id,
                    registry_row_no=obj.registry_row_no or str(row_index + 1),
                    rcsme_reg_no=obj.rcsme_reg_no or "",
                    decree_no=obj.decree_no or "",
                    external_military_no=external_no,
                    intake_date=intake_date or obj.intake_date,
                    decision_date=decision_date or obj.decision_date,
                    investigator=_compact_text(investigator) or obj.investigator,
                    incoming_no=_compact_text(incoming_no) or obj.incoming_no,
                    box_no=_compact_text(box_no) or obj.box_no,
                    conflicts=[],
                )
            else:
                row = _registration_list_new_row(
                    index=row_index + 1,
                    registry_row_no=str(row_index + 1),
                    rcsme_base=next_base,
                    rcsme_suffix=rcsme_suffix,
                    case_year=case_year,
                    external_military_no=external_no,
                    intake_date=intake_date,
                    decision_date=decision_date,
                    investigator=investigator,
                    incoming_no=incoming_no,
                    box_no=box_no,
                )
                next_base += 1
                generated_rows.append((party_no, row))
            if first_rcsme is None:
                first_rcsme = row.rcsme_reg_no
            last_rcsme = row.rcsme_reg_no
            if len(sample_rows) < 25:
                sample_rows.append(row)

        parties.append(
            RegistrationListPartyPreview(
                party_no=party_no,
                case_year=case_year,
                column_letter=column.column_letter,
                object_count=len(column.values),
                first_external_military_no=column.values[0] if column.values else None,
                last_external_military_no=column.values[-1] if column.values else None,
                first_rcsme_reg_no=first_rcsme,
                last_rcsme_reg_no=last_rcsme,
                existing_party_id=existing_party.id if existing_party else None,
                existing_object_count=existing_count,
                will_create_party=will_create_party,
                status=status,
                warnings=party_warnings,
                sample_rows=sample_rows,
            )
        )

    if generated_rows:
        generated_rcsme = [row.rcsme_reg_no for _party_no, row in generated_rows]
        generated_decrees = [row.decree_no for _party_no, row in generated_rows]
        existing_numbers = (
            await session.execute(
                select(RegistryObject.rcsme_reg_no, RegistryObject.decree_no).where(
                    or_(
                        RegistryObject.decree_no.in_(generated_decrees),
                        (RegistryObject.case_year == case_year) & RegistryObject.rcsme_reg_no.in_(generated_rcsme),
                    )
                )
            )
        ).all()
        existing_rcsme = {rcsme for rcsme, _decree in existing_numbers if rcsme}
        existing_decrees = {decree for _rcsme, decree in existing_numbers if decree}
        for party_no, row in generated_rows:
            row_conflicts: list[str] = []
            if row.rcsme_reg_no in existing_rcsme:
                row_conflicts.append("№ рег РЦСМЭ уже есть")
            if row.decree_no in existing_decrees:
                row_conflicts.append("№ постановления уже есть")
            if row_conflicts:
                row.conflicts.extend(row_conflicts)
                conflicts.append(f"Партия {party_no}, {row.rcsme_reg_no}: {', '.join(row_conflicts)}")

    if conflicts:
        warnings.append("Исправьте конфликты или выберите режим обновления для существующих партий.")
    preview = RegistrationListPreviewOut(
        upload_id=upload_id,
        filename=filename,
        file_sha256=file_sha256,
        sheet_name=parsed.sheet_name,
        start_party_no=start_party_no,
        case_year=case_year,
        suggested_start_rcsme_reg_no=suggested_start,
        previous_party_no=previous_party_no,
        previous_last_rcsme_reg_no=previous_last,
        party_count=len(parsed.columns),
        total_objects=sum(len(column.values) for column in parsed.columns),
        parties_to_create=sum(1 for item in parties if item.will_create_party),
        existing_parties=sum(1 for item in parties if item.existing_party_id is not None),
        conflicts=conflicts,
        warnings=warnings,
        parties=parties,
    )
    return preview, parsed.columns


@router.post("/registry/preview", response_model=ImportPreviewResponse)
async def registry_preview(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(edit_user),
):
    upload_id, digest, path = await save_upload(file, "registry")
    original_filename = file.filename or Path(path).name
    preview = parse_registry(path)
    party_no = extract_party_no(original_filename)
    case_year = _preview_case_year(preview.rows)
    duplicates = await find_registry_duplicates(session, preview.rows, party_no=party_no, case_year=case_year)
    existing_by_rcsme, existing_by_decree = await existing_object_map(session, preview.rows, case_year)
    existing_row_count = 0
    replace_required_rows: set[int] = set()
    warnings = [*preview.warnings, *registry_quality_warnings(preview.rows)]
    for row in preview.rows:
        if existing_by_rcsme.get(row.get("rcsme_reg_no")) or existing_by_decree.get(row.get("decree_no")):
            existing_row_count += 1
    for item in duplicates:
        if item.get("scope") == "database":
            replace_required_rows.add(int(item["row_number"]))
    if existing_row_count:
        stage_counts = registry_stage_counts(preview.rows)
        stage_total = sum(stage_counts.values())
        warnings.append(
            f"Будут заменены ранее импортированные данные этапов из этого реестра: "
            f"{existing_row_count} объектов, {stage_total} stage-записей из файла."
        )
    cross_party_duplicates = [item for item in duplicates if item.get("scope") == "database_other_party"]
    if cross_party_duplicates:
        warnings.append(
            f"Найдены объекты из других партий: {len(cross_party_duplicates)}; они не будут перенесены в партию {party_no}."
        )
    return ImportPreviewResponse(
        upload_id=upload_id,
        filename=original_filename,
        file_sha256=digest,
        party_no=party_no,
        sheet_name=preview.sheet_name,
        rows_detected=len(preview.rows),
        rows_skipped=len(preview.skipped_rows),
        sample_rows=preview.rows[:20],
        warnings=warnings,
        duplicates=duplicates,
        stage_event_counts=registry_stage_counts(preview.rows),
        party_control=preview.party_control,
        existing_objects_count=existing_row_count,
        new_objects_count=max(len(preview.rows) - existing_row_count, 0),
        replace_required_count=len(replace_required_rows),
    )


@router.post("/registry/commit", response_model=ImportCommitResponse)
async def registry_commit(
    payload: ImportCommitRequest,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    try:
        path = upload_path(payload.upload_id, "registry")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Загруженный файл не найден") from None
    import hashlib

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    metadata = upload_metadata(path)
    filename = metadata.get("original_filename") or path.name
    try:
        batch, warnings = await import_registry_file(
            session,
            path,
            filename,
            digest,
            user,
            duplicate_mode=payload.duplicate_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ImportCommitResponse(
        batch_id=batch.id,
        rows_total=batch.rows_total,
        rows_imported=batch.rows_imported,
        rows_updated=int(batch.import_log_json.get("objects_updated", 0)),
        rows_skipped=batch.rows_skipped,
        stage_events_written=int(batch.import_log_json.get("stage_events_written", 0)),
        warnings=warnings,
    )


@router.post("/registration-list/preview", response_model=RegistrationListPreviewOut)
async def registration_list_preview(
    file: UploadFile = File(...),
    start_party_no: str = Form(...),
    case_year: int = Form(...),
    intake_date: date | None = Form(None),
    decision_date: date | None = Form(None),
    investigator: str | None = Form(None),
    incoming_no: str | None = Form(None),
    box_no: str | None = Form(None),
    duplicate_mode: str = Form("block"),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(edit_user),
):
    if duplicate_mode not in {"block", "update_empty_or_existing"}:
        raise HTTPException(status_code=400, detail="Неизвестный режим импорта")
    upload_id, digest, path = await save_upload(file, "registration_list")
    filename = file.filename or Path(path).name
    preview, _columns = await _build_registration_list_preview(
        session,
        path,
        upload_id=upload_id,
        filename=filename,
        file_sha256=digest,
        start_party_no=start_party_no,
        case_year=case_year,
        intake_date=intake_date,
        decision_date=decision_date,
        investigator=investigator,
        incoming_no=incoming_no,
        box_no=box_no,
        duplicate_mode=duplicate_mode,
    )
    return preview


@router.post("/registration-list/commit", response_model=RegistrationListCommitResponse)
async def registration_list_commit(
    payload: RegistrationListCommitRequest,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    try:
        path = upload_path(payload.upload_id, "registration_list")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Загруженный файл не найден") from None
    metadata = upload_metadata(path)
    filename = metadata.get("original_filename") or path.name
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    preview, columns = await _build_registration_list_preview(
        session,
        path,
        upload_id=payload.upload_id,
        filename=filename,
        file_sha256=digest,
        start_party_no=payload.start_party_no,
        case_year=payload.case_year,
        intake_date=payload.intake_date,
        decision_date=payload.decision_date,
        investigator=payload.investigator,
        incoming_no=payload.incoming_no,
        box_no=payload.box_no,
        duplicate_mode=payload.duplicate_mode,
    )
    if preview.conflicts:
        raise HTTPException(status_code=409, detail="Есть конфликты импорта: " + "; ".join(preview.conflicts[:8]))

    parties_created = 0
    parties_updated = 0
    objects_created = 0
    objects_updated = 0
    warnings = list(preview.warnings)
    affected_party_ids: set[int] = set()

    start_base, suffix = _parse_rcsme_start(preview.suggested_start_rcsme_reg_no)
    next_base = start_base
    start_party_numeric = _parse_positive_int(payload.start_party_no, "Стартовая партия")

    for column_index, column in enumerate(columns):
        party_no = _registration_list_party_no(start_party_numeric, column_index)
        party_result = await session.execute(
            select(Party).where(Party.party_no == party_no, Party.case_year == payload.case_year)
        )
        party = party_result.scalar_one_or_none()
        if not party:
            party = Party(
                party_no=party_no,
                case_year=payload.case_year,
                title=party_no,
                status="active",
                created_by_user_id=user.id,
                object_count=0,
                raw_control_json={},
            )
            session.add(party)
            await session.flush()
            parties_created += 1
            await write_audit(session, user, "party", party.id, "registration_list_create", None, {"party_no": party_no})
        affected_party_ids.add(party.id)

        existing_objects = await _registration_party_objects(session, party.id)
        if existing_objects and payload.duplicate_mode == "block":
            warnings.append(f"Партия {party_no} пропущена: уже содержит {len(existing_objects)} объект(ов).")
            continue
        updated_in_party = 0
        created_in_party = 0
        for value_index, external_military_no in enumerate(column.values):
            if payload.duplicate_mode != "block" and value_index < len(existing_objects):
                obj = existing_objects[value_index]
                before = {
                    "external_military_no": obj.external_military_no,
                    "intake_date": obj.intake_date.isoformat() if obj.intake_date else None,
                    "decision_date": obj.decision_date.isoformat() if obj.decision_date else None,
                    "investigator": obj.investigator,
                    "incoming_no": obj.incoming_no,
                    "box_no": obj.box_no,
                    "object_description": obj.object_description,
                }
                obj.registry_row_no = obj.registry_row_no or str(value_index + 1)
                obj.external_military_no = external_military_no
                if payload.intake_date:
                    obj.intake_date = payload.intake_date
                if payload.decision_date:
                    obj.decision_date = payload.decision_date
                if _compact_text(payload.investigator):
                    obj.investigator = _compact_text(payload.investigator)
                if _compact_text(payload.incoming_no):
                    obj.incoming_no = _compact_text(payload.incoming_no)
                if _compact_text(payload.box_no):
                    obj.box_no = _compact_text(payload.box_no)
                if not _compact_text(obj.object_description):
                    obj.object_description = "кость"
                after = {
                    "external_military_no": obj.external_military_no,
                    "intake_date": obj.intake_date.isoformat() if obj.intake_date else None,
                    "decision_date": obj.decision_date.isoformat() if obj.decision_date else None,
                    "investigator": obj.investigator,
                    "incoming_no": obj.incoming_no,
                    "box_no": obj.box_no,
                    "object_description": obj.object_description,
                }
                if before != after:
                    updated_in_party += 1
                    objects_updated += 1
                continue

            rcsme_reg_no = f"{next_base}-{suffix}"
            decree_no = f"{next_base}-{payload.case_year}"
            obj = RegistryObject(
                party_id=party.id,
                party_no=party.party_no,
                case_year=payload.case_year,
                registry_row_no=str(value_index + 1),
                intake_date=payload.intake_date,
                decision_date=payload.decision_date,
                investigator=_compact_text(payload.investigator),
                incoming_no=_compact_text(payload.incoming_no),
                decree_no=decree_no,
                decree_no_base=number_base(decree_no),
                external_military_no=external_military_no,
                box_no=_compact_text(payload.box_no),
                object_description="кость",
                rcsme_reg_no=rcsme_reg_no,
                rcsme_reg_no_base=number_base(rcsme_reg_no),
                rcsme_reg_no_is_manual=True,
                status="new",
                raw_registry_json={
                    "source": "registration_list",
                    "upload_id": payload.upload_id,
                    "filename": filename,
                    "sheet_name": preview.sheet_name,
                    "column_letter": column.column_letter,
                    "source_row": column.source_rows[value_index] if value_index < len(column.source_rows) else None,
                },
            )
            session.add(obj)
            try:
                await session.flush()
            except IntegrityError as exc:
                await session.rollback()
                raise HTTPException(status_code=409, detail=f"Конфликт номера при создании {rcsme_reg_no}") from exc
            created_in_party += 1
            objects_created += 1
            next_base += 1
        if updated_in_party:
            parties_updated += 1
        await write_audit(
            session,
            user,
            "party",
            party.id,
            "registration_list_import",
            None,
            {
                "filename": filename,
                "objects_created": created_in_party,
                "objects_updated": updated_in_party,
                "column_letter": column.column_letter,
            },
        )
    if affected_party_ids:
        await recalculate_party_counts(session, affected_party_ids)
    await session.commit()
    return RegistrationListCommitResponse(
        parties_created=parties_created,
        parties_updated=parties_updated,
        objects_created=objects_created,
        objects_updated=objects_updated,
        warnings=warnings,
        parties=preview.parties,
    )


@router.delete("/registry/{batch_id}")
async def registry_delete_batch(
    batch_id: int,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(current_user),
):
    if user.role.value != "admin":
        raise HTTPException(status_code=403, detail="Только admin может удалить импорт")
    deleted = await delete_import_batch(session, batch_id, user)
    if not deleted:
        raise HTTPException(status_code=404, detail="Импорт не найден")
    return {"ok": True}


@router.post("/rt/preview", response_model=RtPreviewResponse)
async def rt_preview(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(edit_user),
):
    upload_id, digest, path = await save_upload(file, "rt")
    filename = file.filename or Path(path).name
    preview = parse_rt_preview(path, source_filename=filename)
    sample_rows, matched, unmatched = await rt_preview_rows_with_matches(session, preview.aggregated_samples or [])
    existing = await rt_existing_import_summary(session, sample_rows)
    unmatched_rows = [row for row in sample_rows if not row.get("matched")]
    repeat_samples = [
        {
            "sample_name": row.get("normalized_sample_name") or row.get("sample_name_raw"),
            "parent_rcsme_reg_no": row.get("parent_rcsme_reg_no"),
            "repeat_suffix": row.get("repeat_suffix"),
            "repeat_object_exists": row.get("repeat_object_exists"),
            "will_create_repeat_object": row.get("will_create_repeat_object"),
            "matched": row.get("matched"),
        }
        for row in sample_rows
        if row.get("is_repeat_sample")
    ]
    warnings = list(preview.warnings)
    if existing["existing_rt_count"]:
        warnings.append(f"Уже есть RT-данные по образцам: {existing['existing_rt_count']}. Выберите замену или новую попытку.")
    missing_repeat_parents = [row for row in repeat_samples if not row.get("matched")]
    if missing_repeat_parents:
        warnings.append(f"Повторы без найденного оригинала: {len(missing_repeat_parents)}.")
    return RtPreviewResponse(
        upload_id=upload_id,
        filename=filename,
        file_sha256=digest,
        parser_type=preview.parser_type,
        run_date=preview.run_date,
        quant_method=preview.quant_method,
        columns=preview.columns,
        sample_names=preview.sample_names[:200],
        sample_rows=sample_rows[:200],
        unmatched_samples=unmatched_rows[:200],
        warnings=warnings,
        matched_count=matched,
        unmatched_count=unmatched,
        existing_rt_count=existing["existing_rt_count"],
        existing_rt_samples=existing["existing_rt_samples"][:200],
        repeat_samples=repeat_samples[:200],
    )


async def _match_protocol_objects(session: AsyncSession, rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    numbers = {value for row in rows for value in (row.get("normalized_sample_name"), row.get("sample_object_no")) if value}
    bases = {row.get("sample_base") for row in rows if row.get("sample_base")}
    result = await session.execute(
        select(RegistryObject).where(
            or_(
                RegistryObject.rcsme_reg_no.in_(numbers),
                RegistryObject.decree_no.in_(numbers),
                RegistryObject.rcsme_reg_no_base.in_(bases),
                RegistryObject.decree_no_base.in_(bases),
            )
        )
    )
    by_number: dict[str, RegistryObject] = {}
    by_base: dict[str, RegistryObject] = {}
    for obj in result.scalars().all():
        for key in (obj.rcsme_reg_no, obj.decree_no):
            if key:
                by_number[key] = obj
        for key in (obj.rcsme_reg_no_base, obj.decree_no_base):
            if key:
                by_base[key] = obj

    matched: list[dict] = []
    for row in rows:
        exact = by_number.get(row.get("normalized_sample_name") or "")
        parent = by_number.get(row.get("sample_object_no") or "")
        obj = exact or (None if row.get("repeat_suffix") else parent) or by_base.get(row.get("sample_base") or "")
        parent_obj = parent if row.get("repeat_suffix") else None
        matched.append(
            {
                **row,
                "matched": bool(obj),
                "object_id": obj.id if obj else None,
                "object_rcsme_reg_no": obj.rcsme_reg_no if obj else None,
                "object_decree_no": obj.decree_no if obj else None,
                "party_id": obj.party_id if obj else None,
                "party_no": obj.party_no if obj else None,
                "is_repeat_sample": bool(row.get("repeat_suffix")),
                "repeat_object_exists": bool(exact and row.get("repeat_suffix")),
                "parent_object_id": parent_obj.id if parent_obj else None,
                "parent_rcsme_reg_no": parent_obj.rcsme_reg_no if parent_obj else None,
            }
        )
    return matched


@router.post("/work-protocol/preview", response_model=WorkProtocolPreviewResponse)
async def work_protocol_preview(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(edit_user),
):
    upload_id, digest, path = await save_upload(file, "protocol")
    filename = file.filename or Path(path).name
    preview = parse_work_protocol_preview(path)
    objects = await _match_protocol_objects(session, preview.objects)
    warnings = list(preview.warnings)
    repeat_without_object = [
        row for row in objects
        if row.get("is_repeat_sample") and row.get("parent_object_id") and not row.get("repeat_object_exists")
    ]
    if repeat_without_object:
        warnings.append(
            f"Повторы без отдельной строки объекта: {len(repeat_without_object)}. Они показаны в preview, но применяются только после создания repeat-объекта."
        )
    unmatched = [row for row in objects if not row.get("matched")]
    if unmatched:
        warnings.append(f"Не найдены объекты: {len(unmatched)}")
    return WorkProtocolPreviewResponse(
        upload_id=upload_id,
        filename=filename,
        file_sha256=digest,
        protocol_title=preview.protocol_title,
        protocol_no=preview.protocol_no,
        protocol_name=preview.protocol_name,
        objects=objects,
        plate_cells=preview.plate_cells,
        stage_blocks=[block.__dict__ for block in preview.stage_blocks],
        matched_count=sum(1 for row in objects if row.get("matched")),
        unmatched_count=len(unmatched),
        repeat_count=sum(1 for row in objects if row.get("is_repeat_sample")),
        warnings=warnings,
    )


@router.post("/rt/commit", response_model=RtCommitResponse)
async def rt_commit(
    payload: RtCommitRequest,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    try:
        path = upload_path(payload.upload_id, "rt")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Загруженный файл не найден") from None
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    metadata = upload_metadata(path)
    filename = metadata.get("original_filename") or path.name
    try:
        run, results_written, stage_events_written, unmatched_count, warnings, replaced = await import_rt_file(
            session,
            path,
            filename,
            digest,
            user,
            quant_performer=payload.quant_performer,
            employee_id=payload.employee_id,
            duplicate_mode=payload.duplicate_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RtCommitResponse(
        run_id=run.id,
        results_written=results_written,
        stage_events_written=stage_events_written,
        matched_count=stage_events_written,
        unmatched_count=unmatched_count,
        replaced_results=replaced["replaced_results"],
        replaced_stage_events=replaced["replaced_stage_events"],
        warnings=warnings,
    )


def _detect_electrophoresis_control(filename: str) -> dict | None:
    stem = Path(filename).stem.strip()
    normalized = stem.upper().replace("К", "K")
    normalized = re.sub(r"\s+", " ", normalized)
    match = re.match(r"^(K[+-]|PC|NC)(?:[\s_\-]|$)", normalized)
    if not match:
        return None
    raw_type = match.group(1)
    control_type = {"K+": "K+", "K-": "K-", "PC": "PC", "NC": "NC"}[raw_type]
    display = {"K+": "К+", "K-": "К-", "PC": "PC", "NC": "NC"}[control_type]
    return {
        "sample_name_raw": stem,
        "sample_object_no": None,
        "sample_base": None,
        "repeat_suffix": None,
        "matched": True,
        "is_control": True,
        "control_type": control_type,
        "control_label": display,
        "object_id": None,
        "object_rcsme_reg_no": None,
        "object_decree_no": None,
        "party_no": None,
        "existing_file_count": 0,
        "is_repeat_sample": False,
        "repeat_object_exists": False,
        "will_create_repeat_object": False,
        "parent_object_id": None,
        "parent_rcsme_reg_no": None,
    }


def _dedupe_ints(values: list[int | None]) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        if value is None or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


async def _control_parties(session: AsyncSession, party_ids: list[int]) -> list[Party]:
    if not party_ids:
        return []
    result = await session.execute(select(Party).where(Party.id.in_(party_ids)))
    by_id = {party.id: party for party in result.scalars().all()}
    return [by_id[party_id] for party_id in party_ids if party_id in by_id]


async def _control_existing_count(session: AsyncSession, *, party_ids: list[int], control_type: str, filename: str) -> int:
    if not party_ids:
        return 0
    result = await session.execute(
        select(ElectrophoresisControlFile).where(
            ElectrophoresisControlFile.party_id.in_(party_ids),
            ElectrophoresisControlFile.control_type == control_type,
            or_(
                ElectrophoresisControlFile.filename == filename,
                ElectrophoresisControlFile.raw_json["original_filename"].as_string() == filename,
            ),
        )
    )
    return len(result.scalars().all())


async def _match_pdf_samples(session: AsyncSession, filename: str, case_year: int | None = None) -> list[dict]:
    samples = extract_lab_samples_from_text(filename)
    rows: list[dict] = []
    if not samples:
        return rows
    object_numbers = [value for sample in samples for value in (sample.normalized, sample.object_no) if value]
    bases = [sample.base for sample in samples if sample.base]
    conditions = [
        or_(
            RegistryObject.rcsme_reg_no.in_(object_numbers),
            RegistryObject.decree_no.in_(object_numbers),
            RegistryObject.rcsme_reg_no_base.in_(bases),
            RegistryObject.decree_no_base.in_(bases),
        )
    ]
    if case_year:
        conditions.append(RegistryObject.case_year == case_year)
    result = await session.execute(select(RegistryObject).where(*conditions))
    by_number: dict[str, RegistryObject | None] = {}
    by_base: dict[str, RegistryObject | None] = {}

    def remember(mapping: dict[str, RegistryObject | None], key: str | None, obj: RegistryObject) -> None:
        if not key:
            return
        current = mapping.get(key)
        if current is not None and current.id != obj.id:
            mapping[key] = None
        elif key not in mapping:
            mapping[key] = obj

    for obj in result.scalars().all():
        remember(by_number, obj.rcsme_reg_no, obj)
        remember(by_number, obj.decree_no, obj)
        remember(by_base, obj.rcsme_reg_no_base, obj)
        remember(by_base, obj.decree_no_base, obj)
    for sample in samples:
        exact = by_number.get(sample.normalized or "")
        parent = by_number.get(sample.object_no or "") if sample.repeat_suffix else None
        obj = exact or parent or (None if sample.repeat_suffix else by_base.get(sample.base or ""))
        repeat_object_exists = bool(exact and sample.repeat_suffix)
        parent_obj = parent if sample.repeat_suffix else None
        existing_file_count = 0
        if obj and (not sample.repeat_suffix or repeat_object_exists):
            existing_result = await session.execute(
                select(ElectrophoresisResultFile).where(
                    ElectrophoresisResultFile.object_id == obj.id,
                    or_(
                        ElectrophoresisResultFile.filename == filename,
                        ElectrophoresisResultFile.raw_json["original_filename"].as_string() == filename,
                        ElectrophoresisResultFile.raw_json["sample_name_raw"].as_string() == sample.normalized,
                    ),
                )
            )
            existing_file_count = len(existing_result.scalars().all())
        rows.append(
            {
                "sample_name_raw": sample.normalized,
                "sample_object_no": sample.object_no,
                "sample_base": sample.base,
                "repeat_suffix": sample.repeat_suffix,
                "matched": bool(obj),
                "object_id": obj.id if obj else None,
                "object_rcsme_reg_no": (
                    sample.normalized if obj and sample.repeat_suffix and not repeat_object_exists else (obj.rcsme_reg_no if obj else None)
                ),
                "object_decree_no": obj.decree_no if obj else None,
                "party_no": obj.party_no if obj else None,
                "existing_file_count": existing_file_count,
                "is_repeat_sample": bool(sample.repeat_suffix),
                "repeat_object_exists": repeat_object_exists,
                "will_create_repeat_object": bool(parent and sample.repeat_suffix and not repeat_object_exists),
                "parent_object_id": parent_obj.id if parent_obj else None,
                "parent_rcsme_reg_no": parent_obj.rcsme_reg_no if parent_obj else None,
            }
        )
    return rows


@router.post("/electrophoresis-pdf/preview", response_model=ElectrophoresisPdfPreviewResponse)
async def electrophoresis_pdf_preview(
    files: list[UploadFile] = File(...),
    case_year: int | None = Form(None),
    party_id: int | None = Form(None),
    control_party_ids: list[int] | None = Form(None),
    session: AsyncSession = Depends(db_session),
    _user: User = Depends(edit_user),
):
    items: list[ElectrophoresisPdfPreviewItem] = []
    total_matched = 0
    total_unmatched = 0
    selected_control_party_ids = _dedupe_ints([party_id, *(control_party_ids or [])])
    selected_control_parties = await _control_parties(session, selected_control_party_ids)
    selected_control_party_nos = [party.party_no for party in selected_control_parties]
    for file in files:
        upload_id, digest, path = await save_upload(file, "electrophoresis")
        filename = file.filename or Path(path).name
        control = _detect_electrophoresis_control(filename)
        warnings = []
        control_count = 0
        if control:
            existing_count = await _control_existing_count(
                session,
                party_ids=[party.id for party in selected_control_parties],
                control_type=control["control_type"],
                filename=filename,
            )
            control["existing_file_count"] = existing_count
            control["control_party_ids"] = [party.id for party in selected_control_parties]
            control["control_party_nos"] = selected_control_party_nos
            control["control_party_count"] = len(selected_control_parties)
            control["party_no"] = ", ".join(selected_control_party_nos) if selected_control_party_nos else None
            samples = [control]
            matched = 0
            unmatched = 0
            control_count = 1
            if not selected_control_parties:
                warnings.append("Выберите партии для сохранения контрольного PDF")
            if existing_count:
                warnings.append(f"Контрольный PDF уже сохранён: {existing_count}. Выберите замену или добавление.")
        else:
            samples = await _match_pdf_samples(session, filename, case_year)
            matched = sum(1 for item in samples if item.get("matched"))
            unmatched = max(len(samples) - matched, 0)
            existing_count = sum(int(item.get("existing_file_count") or 0) for item in samples)
            if not samples:
                unmatched = 1
                warnings.append("В имени PDF не найден номер объекта")
            elif unmatched:
                warnings.append(f"Не найдены объекты: {unmatched}")
            if existing_count:
                warnings.append(f"Уже сохранены PDF для найденных объектов: {existing_count}. Выберите замену или добавление.")
        total_matched += matched
        total_unmatched += unmatched
        items.append(
            ElectrophoresisPdfPreviewItem(
                upload_id=upload_id,
                filename=filename,
                file_sha256=digest,
                samples=samples,
                matched_count=matched,
                unmatched_count=unmatched,
                existing_count=existing_count,
                control_count=control_count,
                warnings=warnings,
            )
        )
    return ElectrophoresisPdfPreviewResponse(
        items=items,
        matched_count=total_matched,
        unmatched_count=total_unmatched,
        existing_count=sum(item.existing_count for item in items),
        control_count=sum(item.control_count for item in items),
    )


@router.post("/electrophoresis-pdf/commit", response_model=ElectrophoresisPdfCommitResponse)
async def electrophoresis_pdf_commit(
    payload: ElectrophoresisPdfCommitRequest,
    session: AsyncSession = Depends(db_session),
    user: User = Depends(edit_user),
):
    if not payload.analysis_date:
        raise HTTPException(status_code=422, detail="Укажите дату анализа фореза")
    performer_name = clean_text(payload.analysis_performer)
    if payload.employee_id:
        employee = await session.get(Employee, payload.employee_id)
        if not employee:
            raise HTTPException(status_code=404, detail="Исполнитель не найден")
        performer_name = employee.full_name
    if not performer_name and not payload.employee_id:
        raise HTTPException(status_code=422, detail="Выберите исполнителя анализа фореза")

    written = 0
    replaced = 0
    control_written = 0
    control_replaced = 0
    matched = 0
    unmatched = 0
    analysis_events_written = 0
    warnings: list[str] = []
    control_party_ids = _dedupe_ints([payload.party_id, *payload.control_party_ids])
    control_parties = await _control_parties(session, control_party_ids)
    if len(control_parties) != len(control_party_ids):
        raise HTTPException(status_code=404, detail="Одна или несколько партий для контрольных PDF не найдены")
    for upload_id in payload.upload_ids:
        mode = payload.file_modes.get(upload_id, payload.duplicate_mode)
        try:
            path = upload_path(upload_id, "electrophoresis")
        except FileNotFoundError:
            warnings.append(f"Файл не найден: {upload_id}")
            continue
        metadata = upload_metadata(path)
        filename = metadata.get("original_filename") or path.name
        control = _detect_electrophoresis_control(filename)
        if control:
            if not control_parties:
                unmatched += 1
                warnings.append(f"Выберите партии для контрольного PDF: {filename}")
                continue
            for party in control_parties:
                existing_result = await session.execute(
                    select(ElectrophoresisControlFile).where(
                        ElectrophoresisControlFile.party_id == party.id,
                        ElectrophoresisControlFile.control_type == control["control_type"],
                        or_(
                            ElectrophoresisControlFile.filename == filename,
                            ElectrophoresisControlFile.raw_json["original_filename"].as_string() == filename,
                        ),
                    )
                )
                existing_files = existing_result.scalars().all()
                if existing_files and mode == "block":
                    warnings.append(f"Контрольный PDF уже сохранён для партии {party.party_no}: {filename}")
                    continue
                if existing_files and mode == "replace":
                    for existing_file in existing_files:
                        await session.delete(existing_file)
                        control_replaced += 1
                        replaced += 1
                control_file = ElectrophoresisControlFile(
                    party_id=party.id,
                    case_year=party.case_year,
                    control_type=control["control_type"],
                    control_label=control["control_label"],
                    filename=filename,
                    file_path=str(path),
                    file_type="pdf",
                    analysis_date=payload.analysis_date,
                    analysis_performer=performer_name,
                    uploaded_by=user.id,
                    raw_json={
                        **control,
                        "upload_id": upload_id,
                        "original_filename": filename,
                        "duplicate_mode": mode,
                        "control_party_id": party.id,
                        "control_party_no": party.party_no,
                    },
                )
                session.add(control_file)
                control_written += 1
                written += 1
            continue

        samples = await _match_pdf_samples(session, filename, payload.case_year)
        if not samples:
            unmatched += 1
            warnings.append(f"В имени PDF не найден номер объекта: {filename}")
            continue
        for sample in samples:
            if not sample.get("object_id"):
                unmatched += 1
                warnings.append(f"Не найден объект для {sample.get('sample_name_raw')}: {filename}")
                continue
            obj = await session.get(RegistryObject, sample["object_id"])
            if obj and sample.get("repeat_suffix") and not sample.get("repeat_object_exists"):
                obj = await ensure_repeat_object(
                    session,
                    obj,
                    sample.get("sample_name_raw"),
                    user,
                    source="electrophoresis_pdf",
                )
            if not obj:
                unmatched += 1
                warnings.append(f"Не найден объект для {sample.get('sample_name_raw')}: {filename}")
                continue
            existing_result = await session.execute(
                select(ElectrophoresisResultFile).where(
                    ElectrophoresisResultFile.object_id == obj.id,
                    or_(
                        ElectrophoresisResultFile.filename == filename,
                        ElectrophoresisResultFile.raw_json["original_filename"].as_string() == filename,
                        ElectrophoresisResultFile.raw_json["sample_name_raw"].as_string() == sample.get("sample_name_raw"),
                    ),
                )
            )
            existing_files = existing_result.scalars().all()
            if existing_files and mode == "block":
                warnings.append(f"PDF уже сохранён для {sample.get('sample_name_raw')}: {filename}")
                continue
            if existing_files and mode == "replace":
                for existing_file in existing_files:
                    old_path = Path(existing_file.file_path)
                    await session.delete(existing_file)
                    replaced += 1
                    if old_path != path:
                        try:
                            old_path.unlink(missing_ok=True)
                        except OSError:
                            warnings.append(f"Не удалось удалить старый PDF-файл: {old_path.name}")
                existing_events = await session.execute(
                    select(StageEvent).where(
                        StageEvent.object_id == obj.id,
                        StageEvent.stage_type == "analysis",
                        StageEvent.source == "electrophoresis_pdf",
                        or_(
                            StageEvent.raw_json["original_filename"].as_string() == filename,
                            StageEvent.raw_json["sample_name_raw"].as_string() == sample.get("sample_name_raw"),
                        ),
                    )
                )
                for event in existing_events.scalars().all():
                    await session.delete(event)
            matched += 1
            pdf_file = ElectrophoresisResultFile(
                object_id=obj.id,
                filename=filename,
                file_path=str(path),
                file_type="pdf",
                uploaded_by=user.id,
                raw_json={**sample, "upload_id": upload_id, "original_filename": filename, "duplicate_mode": mode},
            )
            session.add(pdf_file)
            await session.flush()
            await create_stage_event(
                session,
                obj,
                stage_type="analysis",
                event_date=payload.analysis_date,
                source="electrophoresis_pdf",
                comment=f"PDF фореза: {filename}",
                raw_json={
                    **sample,
                    "upload_id": upload_id,
                    "original_filename": filename,
                    "electrophoresis_file_id": pdf_file.id,
                    "duplicate_mode": mode,
                },
                created_by_user_id=user.id,
                detail_data={"analysis_date": payload.analysis_date},
                performers=[{"employee_id": payload.employee_id, "raw_name": performer_name, "role": "analysis"}],
            )
            analysis_events_written += 1
            written += 1
    await write_audit(
        session,
        user,
        "electrophoresis_result_files",
        "bulk",
        "import",
        None,
        {
            "files_written": written,
            "files_replaced": replaced,
            "control_files_written": control_written,
            "control_files_replaced": control_replaced,
            "analysis_events_written": analysis_events_written,
        },
    )
    await session.commit()
    return ElectrophoresisPdfCommitResponse(
        files_written=written,
        matched_count=matched,
        unmatched_count=unmatched,
        files_replaced=replaced,
        control_files_written=control_written,
        control_files_replaced=control_replaced,
        analysis_events_written=analysis_events_written,
        warnings=warnings,
    )


def _rcsme_fix_target(value: str | None) -> str | None:
    text = normalize_number(value)
    if not text:
        return None
    import re

    match = re.fullmatch(r"(\d{1,8})-20\d{2}", text)
    return f"{match.group(1)}-1" if match else None


async def _rcsme_fix_candidates(session: AsyncSession) -> tuple[list[tuple[RegistryObject, str, bool]], int]:
    result = await session.execute(
        select(RegistryObject).where(
            RegistryObject.rcsme_reg_no.op("~")(r"^[0-9]+-20[0-9]{2}$"),
            RegistryObject.rcsme_reg_no == RegistryObject.decree_no,
            RegistryObject.rcsme_reg_no_is_manual.is_(False),
        )
    )
    objects = result.scalars().all()
    existing = {value for value in (await session.execute(select(RegistryObject.rcsme_reg_no))).scalars().all() if value}
    rows: list[tuple[RegistryObject, str, bool]] = []
    conflicts = 0
    for obj in objects:
        target = _rcsme_fix_target(obj.rcsme_reg_no)
        if not target:
            continue
        conflict = target in existing and target != obj.rcsme_reg_no
        conflicts += 1 if conflict else 0
        rows.append((obj, target, conflict))
    return rows, conflicts


@router.get("/registry/rcsme-fix/preview", response_model=RcsmeFixPreviewResponse)
async def rcsme_fix_preview(
    session: AsyncSession = Depends(db_session),
    user: User = Depends(current_user),
):
    if user.role.value != "admin":
        raise HTTPException(status_code=403, detail="Только admin может исправлять номера")
    rows, conflicts = await _rcsme_fix_candidates(session)
    sample_rows = [
        RcsmeFixPreviewItem(
            id=obj.id,
            party_no=obj.party_no,
            decree_no=obj.decree_no,
            current_rcsme_reg_no=obj.rcsme_reg_no or "",
            suggested_rcsme_reg_no=target,
        )
        for obj, target, conflict in rows[:100]
        if not conflict
    ]
    return RcsmeFixPreviewResponse(total=len(rows), conflicts=conflicts, sample_rows=sample_rows)


@router.post("/registry/rcsme-fix/apply", response_model=RcsmeFixApplyResponse)
async def rcsme_fix_apply(
    session: AsyncSession = Depends(db_session),
    user: User = Depends(current_user),
):
    if user.role.value != "admin":
        raise HTTPException(status_code=403, detail="Только admin может исправлять номера")
    rows, conflicts = await _rcsme_fix_candidates(session)
    fixed = 0
    skipped = 0
    for obj, target, conflict in rows:
        if conflict:
            skipped += 1
            continue
        before = {"rcsme_reg_no": obj.rcsme_reg_no, "rcsme_reg_no_base": obj.rcsme_reg_no_base}
        obj.rcsme_reg_no = target
        obj.rcsme_reg_no_base = number_base(target)
        obj.rcsme_reg_no_is_manual = False
        await write_audit(session, user, "object", obj.id, "fix_rcsme_reg_no", before, {"rcsme_reg_no": target})
        fixed += 1
    await session.commit()
    return RcsmeFixApplyResponse(fixed=fixed, skipped=skipped, conflicts=conflicts)
