from __future__ import annotations

import math
import re
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Party, RegistryObject, User
from app.parsers.normalization import normalize_number, number_base
from app.print_service.models import AutoRegistrationPayload
from app.print_service.services.matching_service import match_documents
from app.print_service.services.stamping_service import apply_stamping_to_validation, default_stamp_config
from app.services.audit import write_audit
from app.services.registry import recalculate_party_counts


LAB_TOKEN_RE = re.compile(r"(?<![0-9A-Za-zА-Яа-яЁё])([A-Za-zА-Яа-яЁё]{1,5}\s*\d{2,})(?![0-9A-Za-zА-Яа-яЁё])")


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


def _document_label(doc: dict[str, Any]) -> str | None:
    stem = Path(str(doc.get("original_name") or "")).stem
    matches = LAB_TOKEN_RE.findall(stem)
    if not matches:
        return None
    return " ".join(matches[-1].split()).lower()


def _external_number(value: str | None) -> str | None:
    text = _compact_text(value)
    if not text:
        return None
    return re.sub(r"\s+", "", text.replace("–", "-").replace("—", "-").replace("−", "-")).lower()


def _external_numbers(payload: AutoRegistrationPayload, documents_count: int) -> list[str]:
    values = [_external_number(value) for value in payload.external_military_numbers]
    numbers = [value for value in values if value]
    if not numbers:
        return []
    if len(numbers) != documents_count:
        diff = documents_count - len(numbers)
        if diff > 0:
            detail = f"Не совпадает количество DOCX и номеров № в в/ч №522: документов {documents_count}, номеров {len(numbers)}. Не хватает {diff}."
        else:
            detail = f"Не совпадает количество DOCX и номеров № в в/ч №522: документов {documents_count}, номеров {len(numbers)}. Лишних номеров: {abs(diff)}."
        raise HTTPException(status_code=400, detail=detail)
    return numbers


def _documents_by_id(documents: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(doc["id"]): doc for doc in documents}


def _ordered_documents_from_external_numbers(
    documents: list[dict[str, Any]],
    external_numbers: list[str],
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, Any] | None]:
    if not external_numbers:
        return documents, {}, None
    matching = match_documents("\n".join(external_numbers), documents)
    if not matching["can_build"]:
        return [], {}, matching
    by_id = _documents_by_id(documents)
    ordered: list[dict[str, Any]] = []
    external_by_doc_id: dict[str, str] = {}
    for entry in matching["entries"]:
        doc_id = entry.get("doc_id")
        if not doc_id:
            continue
        ordered.append(by_id[doc_id])
        external_by_doc_id[doc_id] = entry["number"]
    return ordered, external_by_doc_id, matching


def _party_no(start_party_no: int, offset: int) -> str:
    return str(start_party_no + offset)


def _object_snapshot(obj: RegistryObject) -> dict[str, Any]:
    return {
        "id": obj.id,
        "party_id": obj.party_id,
        "party_no": obj.party_no,
        "case_year": obj.case_year,
        "registry_row_no": obj.registry_row_no,
        "rcsme_reg_no": obj.rcsme_reg_no,
        "decree_no": obj.decree_no,
        "external_military_no": obj.external_military_no,
        "intake_date": obj.intake_date.isoformat() if obj.intake_date else None,
        "decision_date": obj.decision_date.isoformat() if obj.decision_date else None,
        "investigator": obj.investigator,
        "incoming_no": obj.incoming_no,
        "box_no": obj.box_no,
        "status": obj.status,
    }


async def registration_start_hint(session: AsyncSession, case_year: int) -> tuple[str, str | None, str | None]:
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


async def _existing_party_counts(
    session: AsyncSession, party_nos: list[str], case_year: int
) -> dict[str, tuple[Party, int]]:
    if not party_nos:
        return {}
    parties = (
        await session.execute(select(Party).where(Party.case_year == case_year, Party.party_no.in_(party_nos)))
    ).scalars().all()
    counts: dict[str, tuple[Party, int]] = {}
    for party in parties:
        object_rows = await session.execute(
            select(RegistryObject.id).where(RegistryObject.party_id == party.id, RegistryObject.status != "archived")
        )
        counts[party.party_no] = (party, len(object_rows.all()))
    return counts


async def build_auto_registration_preview(
    session: AsyncSession,
    documents: list[dict[str, Any]],
    payload: AutoRegistrationPayload,
) -> dict[str, Any]:
    if not documents:
        raise HTTPException(status_code=400, detail="В задаче нет загруженных DOCX")
    if payload.case_year < 1900 or payload.case_year > 2200:
        raise HTTPException(status_code=400, detail="Год должен быть в диапазоне 1900–2200")
    start_party = _parse_positive_int(payload.start_party_no, "Стартовая партия")
    external_numbers = _external_numbers(payload, len(documents))
    external_source = "list" if external_numbers else "filename"
    ordered_documents, external_by_doc_id, matching = _ordered_documents_from_external_numbers(documents, external_numbers)
    suggested_start, previous_party_no, previous_last = await registration_start_hint(session, payload.case_year)
    start_base, suffix = _parse_rcsme_start(payload.start_rcsme_reg_no or suggested_start)
    conflicts: list[str] = []
    warnings: list[str] = []
    if matching:
        conflicts.extend(f"№ в в/ч №522: {error}" for error in matching.get("blocking_errors") or [])
        warnings.extend(matching.get("warnings") or [])
    if conflicts:
        return {
            "start_party_no": payload.start_party_no,
            "case_year": payload.case_year,
            "documents_per_party": payload.documents_per_party,
            "suggested_start_rcsme_reg_no": suggested_start,
            "requested_start_rcsme_reg_no": payload.start_rcsme_reg_no or suggested_start,
            "previous_party_no": previous_party_no,
            "previous_last_rcsme_reg_no": previous_last,
            "party_count": 0,
            "total_objects": 0,
            "parties_to_create": 0,
            "existing_parties": 0,
            "stamp_field": payload.stamp_field,
            "external_military_no_source": external_source,
            "external_military_no_count": len(external_numbers),
            "matching": matching,
            "conflicts": conflicts,
            "warnings": warnings,
            "parties": [],
            "rows": [],
        }

    party_count = math.ceil(len(ordered_documents) / payload.documents_per_party)
    party_nos = [_party_no(start_party, index) for index in range(party_count)]
    existing = await _existing_party_counts(session, party_nos, payload.case_year)

    rows: list[dict[str, Any]] = []
    parties: list[dict[str, Any]] = []
    next_base = start_base

    for party_index, party_no in enumerate(party_nos):
        start = party_index * payload.documents_per_party
        docs = ordered_documents[start : start + payload.documents_per_party]
        existing_party, existing_count = existing.get(party_no, (None, 0))
        party_warnings: list[str] = []
        if existing_party and existing_count:
            message = f"Партия {party_no} за {payload.case_year} уже содержит {existing_count} объект(ов)"
            conflicts.append(message)
            party_warnings.append(message)
        elif existing_party:
            party_warnings.append("Партия уже существует, но активных объектов в ней нет.")
        first_rcsme: str | None = None
        last_rcsme: str | None = None
        first_decree: str | None = None
        last_decree: str | None = None
        sample_rows: list[dict[str, Any]] = []
        for local_index, doc in enumerate(docs, start=1):
            rcsme_reg_no = f"{next_base}-{suffix}"
            decree_no = f"{next_base}-{payload.case_year}"
            row = {
                "index": local_index,
                "global_index": start + local_index,
                "party_no": party_no,
                "case_year": payload.case_year,
                "doc_id": doc["id"],
                "document_name": doc["original_name"],
                "registry_row_no": str(local_index),
                "rcsme_reg_no": rcsme_reg_no,
                "decree_no": decree_no,
                "external_military_no": external_by_doc_id.get(doc["id"]) if external_numbers else _document_label(doc),
                "external_military_no_source": external_source,
                "stamp_label": decree_no if payload.stamp_field == "decree_no" else rcsme_reg_no,
                "conflicts": [],
            }
            rows.append(row)
            if first_rcsme is None:
                first_rcsme = rcsme_reg_no
                first_decree = decree_no
            last_rcsme = rcsme_reg_no
            last_decree = decree_no
            if len(sample_rows) < 25:
                sample_rows.append(row)
            next_base += 1
        parties.append(
            {
                "party_no": party_no,
                "case_year": payload.case_year,
                "object_count": len(docs),
                "first_rcsme_reg_no": first_rcsme,
                "last_rcsme_reg_no": last_rcsme,
                "first_decree_no": first_decree,
                "last_decree_no": last_decree,
                "existing_party_id": existing_party.id if existing_party else None,
                "existing_object_count": existing_count,
                "will_create_party": existing_party is None,
                "status": "конфликт" if existing_party and existing_count else ("существует пустая" if existing_party else "будет создана"),
                "warnings": party_warnings,
                "sample_rows": sample_rows,
            }
        )

    if rows:
        existing_numbers = (
            await session.execute(
                select(RegistryObject.rcsme_reg_no, RegistryObject.decree_no).where(
                    or_(
                        RegistryObject.decree_no.in_([row["decree_no"] for row in rows]),
                        and_(
                            RegistryObject.case_year == payload.case_year,
                            RegistryObject.rcsme_reg_no.in_([row["rcsme_reg_no"] for row in rows]),
                        ),
                    )
                )
            )
        ).all()
        existing_rcsme = {rcsme for rcsme, _decree in existing_numbers if rcsme}
        existing_decrees = {decree for _rcsme, decree in existing_numbers if decree}
        for row in rows:
            if row["rcsme_reg_no"] in existing_rcsme:
                row["conflicts"].append("№ рег РЦСМЭ уже есть")
            if row["decree_no"] in existing_decrees:
                row["conflicts"].append("№ постановления уже есть")
            if row["conflicts"]:
                conflicts.append(f"Партия {row['party_no']}, {row['rcsme_reg_no']}: {', '.join(row['conflicts'])}")

    without_external = sum(1 for row in rows if not row["external_military_no"])
    if without_external and not external_numbers:
        warnings.append(f"Для {without_external} DOCX не удалось извлечь № в в/ч №522 из имени файла.")
    if external_numbers:
        duplicates = len(external_numbers) - len(set(external_numbers))
        if duplicates:
            warnings.append(f"В списке № в в/ч №522 есть повторяющиеся значения: {duplicates}.")
    if conflicts:
        warnings.append("Выберите свободную стартовую партию или начальный № рег РЦСМЭ.")

    return {
        "start_party_no": payload.start_party_no,
        "case_year": payload.case_year,
        "documents_per_party": payload.documents_per_party,
        "suggested_start_rcsme_reg_no": suggested_start,
        "requested_start_rcsme_reg_no": payload.start_rcsme_reg_no or suggested_start,
        "previous_party_no": previous_party_no,
        "previous_last_rcsme_reg_no": previous_last,
        "party_count": len(parties),
        "total_objects": len(rows),
        "parties_to_create": sum(1 for item in parties if item["will_create_party"]),
        "existing_parties": sum(1 for item in parties if item["existing_party_id"] is not None),
        "stamp_field": payload.stamp_field,
        "external_military_no_source": external_source,
        "external_military_no_count": len(external_numbers),
        "matching": matching,
        "conflicts": conflicts,
        "warnings": warnings,
        "parties": parties,
        "rows": rows,
    }


def build_registration_validation(documents: list[dict[str, Any]], preview: dict[str, Any], stamping: dict[str, Any] | None) -> dict[str, Any]:
    by_id = {doc["id"]: doc for doc in documents}
    entries: list[dict[str, Any]] = []
    labels: list[str] = []
    for order, row in enumerate(preview["rows"], start=1):
        doc = by_id.get(row["doc_id"])
        labels.append(row["stamp_label"])
        entries.append(
            {
                "order": order,
                "line": order,
                "number": row["external_military_no"] or row["decree_no"],
                "matched_file": doc["original_name"] if doc else row["document_name"],
                "doc_id": row["doc_id"],
                "status": "Готов",
                "blocking": False,
                "warnings": [],
                "error": "",
                "pages": None,
                "page_size": "",
                "conversion_status": "Ожидает",
                "party_no": row["party_no"],
                "rcsme_reg_no": row["rcsme_reg_no"],
                "decree_no": row["decree_no"],
                "external_military_no": row["external_military_no"],
            }
        )
    stamp_config = default_stamp_config()
    stamp_config.update(stamping or {})
    stamp_config["enabled"] = True
    stamp_config["source"] = "registration"
    stamp_config["text"] = "\n".join(labels)
    stamp_config.setdefault("style", {})
    validation = {
        "mode": "registration",
        "entries": entries,
        "unused_documents": [],
        "warnings": list(preview.get("warnings") or []),
        "blocking_errors": [],
        "can_build": bool(entries),
        "total": len(entries),
        "registration": {
            "case_year": preview["case_year"],
            "party_count": preview["party_count"],
            "total_objects": preview["total_objects"],
            "stamp_field": preview["stamp_field"],
        },
    }
    return apply_stamping_to_validation(validation, stamp_config)


async def apply_auto_registration(
    session: AsyncSession,
    user: User,
    documents: list[dict[str, Any]],
    payload: AutoRegistrationPayload,
) -> tuple[dict[str, Any], dict[str, Any]]:
    preview = await build_auto_registration_preview(session, documents, payload)
    if preview["conflicts"]:
        raise HTTPException(status_code=409, detail="Есть конфликты регистрации: " + "; ".join(preview["conflicts"][:8]))
    party_map: dict[str, Party] = {}
    for party_preview in preview["parties"]:
        party_result = await session.execute(
            select(Party).where(Party.party_no == party_preview["party_no"], Party.case_year == payload.case_year)
        )
        party = party_result.scalar_one_or_none()
        if not party:
            party = Party(
                party_no=party_preview["party_no"],
                case_year=payload.case_year,
                title=party_preview["party_no"],
                status="active",
                created_by_user_id=user.id,
                object_count=0,
                raw_control_json={},
            )
            session.add(party)
            await session.flush()
            await write_audit(session, user, "party", party.id, "print_registration_create", None, {"party_no": party.party_no})
        party_map[party.party_no] = party

    created = 0
    affected_party_ids: set[int] = set()
    for row in preview["rows"]:
        party = party_map[row["party_no"]]
        obj = RegistryObject(
            party_id=party.id,
            party_no=party.party_no,
            case_year=payload.case_year,
            registry_row_no=row["registry_row_no"],
            intake_date=payload.intake_date,
            decision_date=payload.decision_date,
            investigator=_compact_text(payload.investigator),
            incoming_no=_compact_text(payload.incoming_no),
            decree_no=row["decree_no"],
            decree_no_base=number_base(row["decree_no"]),
            external_military_no=row["external_military_no"],
            box_no=_compact_text(payload.box_no),
            object_description="кость",
            rcsme_reg_no=row["rcsme_reg_no"],
            rcsme_reg_no_base=number_base(row["rcsme_reg_no"]),
            rcsme_reg_no_is_manual=True,
            status="new",
            raw_registry_json={
                "source": "print_registration",
                "document_id": row["doc_id"],
                "document_name": row["document_name"],
                "stamp_label": row["stamp_label"],
            },
        )
        session.add(obj)
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(status_code=409, detail=f"Конфликт номера при создании {row['rcsme_reg_no']}") from exc
        row["object_id"] = obj.id
        created += 1
        affected_party_ids.add(party.id)
        await write_audit(session, user, "object", obj.id, "print_registration_create", None, _object_snapshot(obj))
    if affected_party_ids:
        await recalculate_party_counts(session, affected_party_ids)
    await write_audit(
        session,
        user,
        "print_job",
        None,
        "print_registration_apply",
        None,
        {"objects_created": created, "party_count": preview["party_count"], "case_year": payload.case_year},
    )
    await session.commit()
    validation = build_registration_validation(documents, preview, payload.stamping)
    preview["objects_created"] = created
    return preview, validation
