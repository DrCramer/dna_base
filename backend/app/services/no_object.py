from __future__ import annotations

import re

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
    "пустой конверт",
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


def _control_token_base(value: str) -> str:
    return re.sub(r"\s*(?:\[[^\]]+\]|\([^)]+\))\s*$", "", value.strip()).strip().casefold()


def control_token_matches_object(value: str, obj: RegistryObject) -> bool:
    external_military_no = object_external_military_no(obj)
    if not external_military_no:
        return False
    normalized = value.strip().casefold()
    external = external_military_no.strip().casefold()
    if _control_token_base(value) != external:
        return False
    if normalized == external:
        return True
    reg_no = (obj.rcsme_reg_no or "").strip().casefold()
    object_hint = f"#{obj.id}"
    return bool((reg_no and reg_no in normalized) or object_hint in normalized)


def has_no_object_marker(value: str | None) -> bool:
    text = (value or "").casefold()
    return any(marker in text for marker in NO_OBJECT_MARKERS)


def object_description(obj: RegistryObject) -> str | None:
    parent = obj.__dict__.get("parent_object") if obj.parent_object_id else None
    return obj.object_description or (parent.object_description if parent else None)


def object_external_military_no(obj: RegistryObject) -> str | None:
    parent = obj.__dict__.get("parent_object") if obj.parent_object_id else None
    return obj.external_military_no or (parent.external_military_no if parent else None)


def object_decree_no(obj: RegistryObject) -> str | None:
    parent = obj.__dict__.get("parent_object") if obj.parent_object_id else None
    return obj.decree_no or (parent.decree_no if parent else None)


def object_is_no_object(obj: RegistryObject, control_numbers: set[str] | None = None) -> bool:
    by_control = any(control_token_matches_object(token, obj) for token in (control_numbers or set()))
    parent = obj.__dict__.get("parent_object") if obj.parent_object_id else None
    empty_envelope = bool(obj.empty_envelope or (parent.empty_envelope if parent else False))
    return empty_envelope or has_no_object_marker(object_description(obj)) or by_control


def object_is_consumed(obj: RegistryObject) -> bool:
    # A materialized repeat is a separate working row and can have its own
    # remaining material even when the original object has been consumed.
    return bool(obj.is_consumed)


def object_is_no_decree(obj: RegistryObject, control_numbers: set[str] | None = None) -> bool:
    by_control = any(control_token_matches_object(token, obj) for token in (control_numbers or set()))
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
