from datetime import date
from types import SimpleNamespace

import pytest

from app.services.protocol_plate import build_protocol_layouts
from app.services.protocols import build_protocol_dilutions, protocol_object_snapshots
from app.services.realtime_details import get_latest_realtime_details, pick_latest_realtime_event


def realtime_event(
    event_id: int,
    *,
    object_id: int = 1,
    attempt_no: int = 1,
    event_date: date = date(2026, 9, 1),
    small_quantity: float | None = None,
    long_quantity: float | None = None,
    y_quantity: float | None = None,
    is_cancelled: bool = False,
):
    detail = SimpleNamespace(
        small_quantity=small_quantity,
        long_quantity=long_quantity,
        y_quantity=y_quantity,
        ct_cq=27.4,
        di=0.8,
        ipc=29.1,
    )
    return SimpleNamespace(
        id=event_id,
        object_id=object_id,
        stage_type="realtime",
        attempt_no=attempt_no,
        event_date=event_date,
        is_cancelled=is_cancelled,
        realtime_detail=detail,
    )


class ScalarResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return iter(self.values)


class RowsResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class QueueSession:
    def __init__(self, *results):
        self.results = list(results)

    async def execute(self, _statement):
        return self.results.pop(0)


def test_latest_active_realtime_attempt_is_selected():
    events = [
        realtime_event(10, attempt_no=1, small_quantity=0.2),
        realtime_event(11, attempt_no=2, small_quantity=0.7),
    ]

    latest = pick_latest_realtime_event(events)

    assert latest.id == 11
    assert latest.realtime_detail.small_quantity == 0.7


def test_cancelled_latest_realtime_attempt_is_ignored():
    events = [
        realtime_event(10, attempt_no=1, small_quantity=0.2),
        realtime_event(11, attempt_no=2, small_quantity=0.7, is_cancelled=True),
    ]

    latest = pick_latest_realtime_event(events)

    assert latest.id == 10
    assert latest.realtime_detail.small_quantity == 0.2


@pytest.mark.asyncio
async def test_resolver_returns_latest_active_realtime_detail_for_each_object():
    session = QueueSession(
        ScalarResult(
            [
                realtime_event(10, object_id=1, attempt_no=1, small_quantity=0.2),
                realtime_event(11, object_id=1, attempt_no=2, small_quantity=0.7),
                realtime_event(20, object_id=2, small_quantity=0.4),
            ]
        )
    )

    resolved = await get_latest_realtime_details(session, [1, 2])

    assert resolved[1].event_id == 11
    assert resolved[1].detail.small_quantity == 0.7
    assert resolved[2].event_id == 20
    assert resolved[2].detail.small_quantity == 0.4


@pytest.mark.asyncio
async def test_protocol_snapshot_uses_small_quantity_without_long_or_y_fallback():
    obj = SimpleNamespace(
        id=1,
        party_id=7,
        party_no="206",
        case_year=2026,
        rcsme_reg_no="7606-1",
        decree_no="12",
        external_military_no="522",
        object_type="кость",
        object_description="горелая кость",
        box_no="3",
        status="active",
    )
    event = realtime_event(
        15,
        small_quantity=None,
        long_quantity=4.2,
        y_quantity=3.1,
    )
    session = QueueSession(
        RowsResult([(obj, "206")]),
        ScalarResult([event]),
        RowsResult([(1, "realtime")]),
    )

    snapshots = await protocol_object_snapshots(session, [1])

    assert snapshots[0]["rt"] == {
        "event_id": 15,
        "small_quantity": None,
        "long_quantity": 4.2,
        "y_quantity": 3.1,
        "concentration": None,
        "ct_cq": 27.4,
        "di": 0.8,
        "ipc": 29.1,
    }


def test_dilutions_use_sample_wells_from_pcr_layout():
    objects = [
        {"id": 1, "rcsme_reg_no": "7606-1", "rt": {"concentration": 1.0}},
        {"id": 2, "rcsme_reg_no": "7606-2", "rt": {"concentration": 0.05}},
    ]
    layouts = build_protocol_layouts(objects, {"nc_enabled": False})

    dilutions = build_protocol_dilutions(
        objects,
        layouts["pcr"]["plates"],
        target_concentration=0.1,
        source_dna_volume=3,
        dilution_one_volume=10,
        threshold=100,
    )

    assert [(item["plate_index"], item["well"]) for item in dilutions] == [(1, "B1"), (1, "C1")]
    assert dilutions[0]["total_factor"] == 10
    assert dilutions[0]["steps"] == [{"factor": 10.0, "dna_volume": 3, "water_volume": 27.0}]
    assert dilutions[1]["steps"] == []
