from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Party, RegistryObject


NO_OBJECT_MARKERS = (
    "нет объекта",
    "нет объект",
    "без объекта",
    "объект отсутствует",
    "отсутствует объект",
    "нет биоматериала",
)


def control_no_tokens(value: str | None) -> set[str]:
    text = (value or "").strip()
    if not text:
        return set()
    return {
        token.strip().casefold()
        for chunk in text.replace("\r", "\n").replace(";", ",").split(",")
        for token in chunk.split("\n")
        if token.strip()
    }


def has_no_object_marker(value: str | None) -> bool:
    text = (value or "").casefold()
    return any(marker in text for marker in NO_OBJECT_MARKERS)


def object_description(obj: RegistryObject) -> str | None:
    parent = obj.parent_object
    return obj.object_description or (parent.object_description if parent else None)


def object_external_military_no(obj: RegistryObject) -> str | None:
    parent = obj.parent_object
    return obj.external_military_no or (parent.external_military_no if parent else None)


def object_decree_no(obj: RegistryObject) -> str | None:
    parent = obj.parent_object
    return obj.decree_no or (parent.decree_no if parent else None)


def object_is_no_object(obj: RegistryObject, control_numbers: set[str] | None = None) -> bool:
    external_military_no = object_external_military_no(obj)
    by_control = bool(external_military_no and external_military_no.strip().casefold() in (control_numbers or set()))
    return has_no_object_marker(object_description(obj)) or by_control


def object_is_no_decree(obj: RegistryObject, control_numbers: set[str] | None = None) -> bool:
    external_military_no = object_external_military_no(obj)
    by_control = bool(external_military_no and external_military_no.strip().casefold() in (control_numbers or set()))
    return not bool((object_decree_no(obj) or "").strip()) or by_control


async def party_no_object_controls(session: AsyncSession, party_ids: list[int]) -> dict[int, set[str]]:
    if not party_ids:
        return {}
    result = await session.execute(select(Party).where(Party.id.in_(party_ids)))
    return {
        party.id: control_no_tokens(party.control_decree_without_object)
        for party in result.scalars().all()
    }


async def party_no_decree_controls(session: AsyncSession, party_ids: list[int]) -> dict[int, set[str]]:
    if not party_ids:
        return {}
    result = await session.execute(select(Party).where(Party.id.in_(party_ids)))
    return {
        party.id: control_no_tokens(party.control_object_without_decree)
        for party in result.scalars().all()
    }
