from unittest.mock import AsyncMock

import pytest

from app.api import stage_table as stage_table_api
from app.api import work_sessions as work_sessions_api
from app.models import RegistryObject
from app.services.no_object import object_is_consumed, object_is_no_object


def _object(**values) -> RegistryObject:
    return RegistryObject(
        rcsme_reg_no=values.pop("rcsme_reg_no", "1-1"),
        empty_envelope=values.pop("empty_envelope", False),
        is_consumed=values.pop("is_consumed", False),
        novosib=values.pop("novosib", False),
        **values,
    )


def test_empty_envelope_is_treated_as_no_object() -> None:
    assert object_is_no_object(_object(empty_envelope=True)) is True
    assert object_is_no_object(_object(object_description="Пустой конверт")) is True
    assert object_is_no_object(_object(object_description="кость")) is False


def test_consumed_flag_is_explicit_per_repeat_object() -> None:
    parent = _object(rcsme_reg_no="1-1", is_consumed=True)
    repeat = _object(rcsme_reg_no="1-1x", parent_object_id=1, repeat_suffix="x")
    repeat.__dict__["parent_object"] = parent

    assert object_is_consumed(parent) is True
    assert object_is_consumed(repeat) is False


def test_novosib_does_not_make_object_unavailable() -> None:
    obj = _object(novosib=True)

    assert object_is_no_object(obj) is False
    assert object_is_consumed(obj) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("module", [stage_table_api, work_sessions_api])
async def test_consumed_object_is_editable_only_during_sample_prep(monkeypatch, module) -> None:
    consumed = _object(is_consumed=True)
    monkeypatch.setattr(module, "party_no_object_controls", AsyncMock(return_value={}))

    prep_rows, _, prep_consumed = await module._editable_stage_objects(None, [consumed], "sample_prep")
    later_rows, _, later_consumed = await module._editable_stage_objects(None, [consumed], "dna_extraction")

    assert prep_rows == [consumed]
    assert prep_consumed == 0
    assert later_rows == []
    assert later_consumed == 1
