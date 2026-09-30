from datetime import date, datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from openpyxl import load_workbook

from app.api.protocols import list_protocols
from app.schemas.protocols import ProtocolCreateRequest, ProtocolPreviewRequest, ProtocolUpdateRequest
from app.services import protocols
from app.services.protocol_excel import build_protocol_workbook


@pytest.mark.parametrize("schema", [ProtocolPreviewRequest, ProtocolCreateRequest, ProtocolUpdateRequest])
def test_selection_is_optional_and_object_ids_are_unique(schema):
    payload = schema(protocol_date="2026-09-30", protocol_no=1, name="test", object_ids=[2, 1, 2])
    assert payload.object_ids == [2, 1]
    assert payload.selection is None


def test_global_count_accepts_legacy_ids_without_counting_stages():
    objects = [{"id": 1, "stage_type": stage} for stage in protocols.STAGE_ORDER]
    objects += [{"object_id": 1}, {"object_id": 2}, {"id": None}, {}]
    assert protocols.protocol_object_count(objects) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("numbers", [[], ["3001-1", "3021-1"]])
async def test_snapshot_preserves_criteria_and_actual_manual_selection(monkeypatch, numbers):
    objects = [{"id": 1, "rcsme_reg_no": "3001-1"}, {"id": 21, "rcsme_reg_no": "3021-1"}]
    monkeypatch.setattr(protocols, "protocol_object_snapshots", AsyncMock(return_value=objects))
    stages = [{"stage_type": stage, "enabled": True, "sequencer_name": None} for stage in protocols.STAGE_ORDER]
    monkeypatch.setattr(protocols, "_stage_snapshots", AsyncMock(return_value=(stages, {})))
    criteria = dict(case_year=2026, party_ids=[205, 206], rcsme_from=None if numbers else "3001-1", rcsme_to=None if numbers else "3020-1", description="кость", numbers=numbers)
    payload = ProtocolCreateRequest(protocol_date="2026-09-30", protocol_no=1, name="test", object_ids=[1, 21, 1], selection=criteria, dilution={"enabled": False})

    preview = await protocols.build_protocol_snapshot(None, payload)

    assert preview["selected_count"] == 2
    assert preview["snapshot"]["selection"] == criteria
    assert [item["id"] for item in preview["snapshot"]["objects"]] == [1, 21]
    assert len(preview["stages"]) == 4
    assert preview["layouts"]["source"]["plates"][0]["sample_count"] == 2
    assert preview["layouts"]["pcr"]["plates"][0]["sample_count"] == 2
    dirty_snapshot = {**preview["snapshot"], "objects": objects * 4}
    workbook = load_workbook(BytesIO(build_protocol_workbook(dirty_snapshot)))
    assert workbook["Единая_плашка_A4"]["H2"].value == 2


@pytest.mark.asyncio
async def test_archive_counts_unique_snapshot_ids():
    protocol = SimpleNamespace(id=1, series_key="test", protocol_no=1, protocol_date=date(2026, 9, 30), name="test", status="draft", revision_no=1, created_by_user_id=None, updated_at=datetime.now(timezone.utc), snapshot_json={"objects": [{"id": 1}, {"object_id": 1}, {"id": 1}, {"id": 2}], "stages": []})
    session = SimpleNamespace(execute=AsyncMock(side_effect=[SimpleNamespace(scalar_one=lambda: 1), SimpleNamespace(scalars=lambda: [protocol])]))

    result = await list_protocols(year=None, limit=50, offset=0, session=session, _user=None)

    assert result.items[0].object_count == 2
