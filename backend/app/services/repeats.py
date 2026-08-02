from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RegistryObject, User
from app.parsers.normalization import LabSampleNumber, normalize_lab_sample, number_base
from app.services.audit import write_audit


def repeat_sort_suffix(value: str | None) -> tuple[int, str]:
    if not value:
        return (0, "")
    if value == "x":
        return (1, value)
    if value == "*":
        return (2, value)
    return (3, value)


def _repeat_snapshot(obj: RegistryObject) -> dict[str, Any]:
    return {
        "id": obj.id,
        "rcsme_reg_no": obj.rcsme_reg_no,
        "party_id": obj.party_id,
        "party_no": obj.party_no,
        "case_year": obj.case_year,
        "parent_object_id": obj.parent_object_id,
        "repeat_suffix": obj.repeat_suffix,
        "status": obj.status,
    }


async def find_parent_object(
    session: AsyncSession,
    *,
    object_no: str | None,
    party_id: int | None = None,
) -> RegistryObject | None:
    if not object_no:
        return None
    stmt = select(RegistryObject).where(RegistryObject.rcsme_reg_no == object_no)
    if party_id:
        stmt = stmt.where(RegistryObject.party_id == party_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def ensure_repeat_object(
    session: AsyncSession,
    parent: RegistryObject,
    sample: LabSampleNumber | str,
    user: User | None = None,
    *,
    source: str = "import",
) -> RegistryObject:
    lab_sample = normalize_lab_sample(sample) if isinstance(sample, str) else sample
    if not lab_sample.repeat_suffix:
        return parent

    repeat_no = lab_sample.normalized or f"{parent.rcsme_reg_no}{lab_sample.repeat_suffix}"
    result = await session.execute(select(RegistryObject).where(RegistryObject.rcsme_reg_no == repeat_no, RegistryObject.case_year == parent.case_year))
    existing = result.scalar_one_or_none()
    if existing:
        before = _repeat_snapshot(existing)
        changed = False
        if existing.parent_object_id != parent.id:
            existing.parent_object_id = parent.id
            changed = True
        if existing.repeat_suffix != lab_sample.repeat_suffix:
            existing.repeat_suffix = lab_sample.repeat_suffix
            changed = True
        if existing.case_year != parent.case_year:
            existing.case_year = parent.case_year
            changed = True
        if not existing.party_id and parent.party_id:
            existing.party_id = parent.party_id
            existing.party_no = parent.party_no
            changed = True
        if changed and user:
            await write_audit(session, user, "object", existing.id, "link_repeat", before, _repeat_snapshot(existing))
        return existing

    repeat = RegistryObject(
        source_import_batch_id=None,
        party_id=parent.party_id,
        parent_object_id=parent.id,
        repeat_suffix=lab_sample.repeat_suffix,
        source_sheet_name=None,
        source_row_number=None,
        party_no=parent.party_no,
        case_year=parent.case_year,
        registry_row_no=parent.registry_row_no,
        intake_date=parent.intake_date,
        decision_date=parent.decision_date,
        investigator=parent.investigator,
        incoming_no=parent.incoming_no,
        decree_no=None,
        decree_no_base=None,
        object_description=parent.object_description,
        external_military_no=parent.external_military_no,
        extraction_note=parent.extraction_note,
        box_no=parent.box_no,
        packages_count=parent.packages_count,
        rcsme_reg_no=repeat_no,
        rcsme_reg_no_base=number_base(repeat_no),
        rcsme_reg_no_is_manual=True,
        object_type=parent.object_type,
        extracted_before=parent.extracted_before,
        not_extracted_before=parent.not_extracted_before,
        registry_filled_by=parent.registry_filled_by,
        status="active" if parent.status != "archived" else "new",
        raw_registry_json={
            "source": source,
            "repeat_of_object_id": parent.id,
            "repeat_of_rcsme_reg_no": parent.rcsme_reg_no,
            "sample_name_raw": lab_sample.raw,
            "normalized_sample_name": lab_sample.normalized,
            "repeat_suffix": lab_sample.repeat_suffix,
        },
    )
    session.add(repeat)
    await session.flush()
    if user:
        await write_audit(session, user, "object", repeat.id, "create_repeat", None, _repeat_snapshot(repeat))
    return repeat
