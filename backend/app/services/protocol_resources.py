import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from fastapi import HTTPException

from app.core.config import get_settings


T = TypeVar("T")


def validate_protocol_size(object_ids: list[int]) -> None:
    maximum = get_settings().protocol_max_objects
    if len(set(object_ids)) > maximum:
        raise HTTPException(
            status_code=400,
            detail=f"В одном протоколе допускается не более {maximum} объектов. Уточните диапазон или разделите выборку на несколько протоколов.",
        )


class ProtocolCalculationGate:
    def __init__(self) -> None:
        self._busy = False

    async def run(self, operation: Callable[[], Awaitable[T]]) -> T:
        if self._busy:
            raise HTTPException(
                status_code=429,
                detail="Сервер уже рассчитывает протокол. Повторите действие после завершения расчёта.",
                headers={"Retry-After": "2"},
            )
        self._busy = True
        try:
            task = asyncio.create_task(operation())
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                # Поток оптимизации не останавливается при отмене HTTP-запроса.
                # Удерживаем слот и DB-session до фактического завершения работы.
                while not task.done():
                    try:
                        await asyncio.shield(task)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
                if not task.cancelled():
                    task.exception()
                raise
        finally:
            self._busy = False


protocol_calculation_gate = ProtocolCalculationGate()
