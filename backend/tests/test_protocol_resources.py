import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.schemas.protocols import ProtocolPreviewRequest
from app.services import protocol_resources, protocols
from app.services.protocol_resources import ProtocolCalculationGate, validate_protocol_size


def test_size_limit_counts_unique_ids(monkeypatch):
    monkeypatch.setattr(protocol_resources, "get_settings", lambda: SimpleNamespace(protocol_max_objects=2))
    validate_protocol_size([1, 2, 1])
    with pytest.raises(HTTPException) as error:
        validate_protocol_size([1, 2, 3])
    assert error.value.status_code == 400
    assert "не более 2 объектов" in error.value.detail


@pytest.mark.asyncio
async def test_large_protocol_is_rejected_before_loading_objects(monkeypatch):
    monkeypatch.setattr(protocol_resources, "get_settings", lambda: SimpleNamespace(protocol_max_objects=2))
    load = AsyncMock()
    monkeypatch.setattr(protocols, "protocol_object_snapshots", load)
    payload = ProtocolPreviewRequest(protocol_date=date.today(), protocol_no=1, name="test", object_ids=[1, 2, 3])
    with pytest.raises(HTTPException):
        await protocols.build_protocol_snapshot(None, payload)
    load.assert_not_awaited()


@pytest.mark.asyncio
async def test_gate_rejects_parallel_work_without_queueing():
    gate = ProtocolCalculationGate()
    started, finish = asyncio.Event(), asyncio.Event()

    async def work():
        started.set()
        await finish.wait()
        return "first"

    first = asyncio.create_task(gate.run(work))
    await started.wait()
    other = AsyncMock(return_value="second")
    with pytest.raises(HTTPException) as error:
        await gate.run(other)
    assert error.value.status_code == 429
    assert error.value.headers == {"Retry-After": "2"}
    other.assert_not_awaited()
    finish.set()
    assert await first == "first"
    assert await gate.run(other) == "second"


@pytest.mark.asyncio
async def test_cancelled_request_holds_slot_until_worker_finishes():
    gate = ProtocolCalculationGate()
    started, finish = asyncio.Event(), asyncio.Event()

    async def work():
        started.set()
        await finish.wait()

    request = asyncio.create_task(gate.run(work))
    await started.wait()
    for _ in range(2):
        request.cancel()
        await asyncio.sleep(0)
        with pytest.raises(HTTPException):
            await gate.run(AsyncMock())
    assert not request.done()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await request
    assert await gate.run(AsyncMock(return_value=3)) == 3


@pytest.mark.asyncio
async def test_gate_releases_slot_after_failure():
    gate = ProtocolCalculationGate()
    with pytest.raises(ValueError):
        await gate.run(AsyncMock(side_effect=ValueError("failed")))
    assert await gate.run(AsyncMock(return_value="ok")) == "ok"


@pytest.mark.asyncio
async def test_cancelled_request_preserves_cancellation_if_worker_fails():
    gate = ProtocolCalculationGate()
    started, finish = asyncio.Event(), asyncio.Event()

    async def work():
        started.set()
        await finish.wait()
        raise ValueError("worker failed")

    request = asyncio.create_task(gate.run(work))
    await started.wait()
    request.cancel()
    await asyncio.sleep(0)
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await request
    assert await gate.run(AsyncMock(return_value="ok")) == "ok"
