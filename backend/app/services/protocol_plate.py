import re
from collections.abc import Iterable, Sequence
from typing import Any


ROWS = "ABCDEFGH"
COLUMNS = range(1, 13)
WELLS = [f"{row}{column}" for column in COLUMNS for row in ROWS]
LADDER_WELLS = ["A1", "A3", "A5", "A7", "A9", "A11"]
PCR_SAMPLE_CAPACITY = 88


def natural_key(value: str | None) -> tuple[Any, ...]:
    return tuple(int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value or ""))


def sort_protocol_objects(objects: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(objects, key=lambda item: (natural_key(item.get("rcsme_reg_no")), item.get("id") or 0))


def source_plate_rules(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    rules = {
        "rows": 8,
        "columns": 12,
        "fill_order": "column",
        "ladder_enabled": False,
        "ladder_wells": LADDER_WELLS,
        "pc_enabled": False,
        "nc_enabled": True,
    }
    rules.update(overrides or {})
    return rules


def _reserved_wells(rules: dict[str, Any]) -> set[str]:
    if not rules.get("ladder_enabled"):
        return set()
    return {well for well in rules.get("ladder_wells", LADDER_WELLS) if well in WELLS}


def plate_capacity(rules: dict[str, Any]) -> int:
    controls = len(_reserved_wells(rules))
    controls += int(bool(rules.get("pc_enabled")))
    controls += int(bool(rules.get("nc_enabled")))
    return max(0, len(WELLS) - controls)


def _well(
    *,
    well: str,
    plate_index: int,
    kind: str,
    order_index: int,
    obj: dict[str, Any] | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    return {
        "plate_index": plate_index,
        "well": well,
        "kind": kind,
        "object_id": obj.get("id") if obj else None,
        "display_name": obj.get("rcsme_reg_no") if obj else label,
        "label": label,
        "order_index": order_index,
        "object_snapshot": obj or None,
    }


def build_plates(
    objects: Sequence[dict[str, Any]],
    rules: dict[str, Any] | None = None,
    *,
    layout_key: str = "source",
) -> dict[str, Any]:
    resolved = source_plate_rules(rules)
    capacity = plate_capacity(resolved)
    if capacity <= 0:
        return {"layout_key": layout_key, "capacity": 0, "plates": [], "warnings": ["Нет свободных лунок для объектов."]}

    chunks = [list(objects[index:index + capacity]) for index in range(0, len(objects), capacity)] or [[]]
    plates: list[dict[str, Any]] = []
    reserved = _reserved_wells(resolved)
    for plate_index, chunk in enumerate(chunks, start=1):
        cells: dict[str, dict[str, Any]] = {}
        for index, well in enumerate(resolved.get("ladder_wells", LADDER_WELLS), start=1):
            if well in reserved:
                cells[well] = _well(
                    well=well, plate_index=plate_index, kind="ladder", order_index=WELLS.index(well), label=f"L{index}"
                )
        free = [well for well in WELLS if well not in reserved]
        cursor = 0
        for obj in chunk:
            well = free[cursor]
            cells[well] = _well(
                well=well, plate_index=plate_index, kind="sample", order_index=WELLS.index(well), obj=obj
            )
            cursor += 1
        for kind, label in (("pc", "PC"), ("nc", "NC")):
            if resolved.get(f"{kind}_enabled"):
                well = free[cursor]
                cells[well] = _well(
                    well=well, plate_index=plate_index, kind=kind, order_index=WELLS.index(well), label=label
                )
                cursor += 1
        wells = [
            cells.get(well)
            or _well(well=well, plate_index=plate_index, kind="empty", order_index=index)
            for index, well in enumerate(WELLS)
        ]
        plates.append({"plate_index": plate_index, "sample_count": len(chunk), "wells": wells})
    return {"layout_key": layout_key, "capacity": capacity, "rules": resolved, "plates": plates, "warnings": []}


def build_pcr_plates(objects: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return build_plates(
        objects,
        {
            "ladder_enabled": True,
            "ladder_wells": LADDER_WELLS,
            "pc_enabled": True,
            "nc_enabled": True,
        },
        layout_key="pcr",
    )


def build_protocol_layouts(
    objects: Sequence[dict[str, Any]], source_rules: dict[str, Any] | None = None
) -> dict[str, Any]:
    ordered_objects = sort_protocol_objects(objects)
    source = build_plates(ordered_objects, source_rules, layout_key="source")
    pcr = build_pcr_plates(ordered_objects)
    warnings = [*source["warnings"], *pcr["warnings"]]
    if len(source["plates"]) > 1:
        warnings.append(f"Для исходной раскладки создано плашек: {len(source['plates'])}.")
    if len(pcr["plates"]) > 1:
        warnings.append(f"Для PCR создано плашек: {len(pcr['plates'])} (по {PCR_SAMPLE_CAPACITY} объектов).")
    return {"source": source, "pcr": pcr, "warnings": warnings}
