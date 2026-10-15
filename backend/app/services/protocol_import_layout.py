from collections import defaultdict
from typing import Any
from fastapi import HTTPException
from app.schemas.protocols import ProtocolImportedWell
from app.services.protocol_plate import WELLS


def apply_imported_layouts(layouts: dict[str, Any], cells: list[ProtocolImportedWell], objects: list[dict[str, Any]]) -> dict[str, Any]:
    if not cells:
        return layouts
    by_id = {obj["id"]: obj for obj in objects}
    grouped: dict[str, dict[int, dict[str, Any]]] = defaultdict(lambda: defaultdict(dict))
    used: dict[str, set[int]] = defaultdict(set)
    for cell in cells:
        plate = grouped[cell.layout_key][cell.plate_index]
        if cell.well in plate:
            raise HTTPException(status_code=400, detail=f"Повтор лунки {cell.well} на плашке {cell.plate_index}")
        obj = by_id.get(cell.source_id) if cell.source_id is not None else None
        if cell.kind == "sample":
            if obj is None or cell.source_id in used[cell.layout_key]:
                raise HTTPException(status_code=400, detail="Импортированная раскладка содержит неизвестный или повторный объект")
            used[cell.layout_key].add(cell.source_id)
        elif cell.source_id is not None:
            raise HTTPException(status_code=400, detail="Контрольная лунка не должна ссылаться на объект")
        plate[cell.well] = {"plate_index": cell.plate_index, "well": cell.well, "kind": cell.kind, "object_id": obj["id"] if obj else None, "source_id": obj["id"] if obj else None, "source_kind": obj.get("source_kind") if obj else None, "display_name": obj.get("display_name") if obj else cell.label, "label": cell.label, "order_index": WELLS.index(cell.well), "object_snapshot": obj}
    result = {**layouts}
    for key, plates in grouped.items():
        if used[key] != set(by_id):
            raise HTTPException(status_code=400, detail=f"Раскладка {key} должна содержать все выбранные объекты. Подтвердите перестроение или исправьте состав.")
        prepared = []
        capacities = []
        for index, wells in sorted(plates.items()):
            sample_count = sum(well["kind"] == "sample" for well in wells.values())
            capacities.append(96 - sum(well["kind"] not in {"sample", "empty"} for well in wells.values()))
            prepared.append({"plate_index": index, "sample_count": sample_count, "wells": [wells.get(well) or {"plate_index": index, "well": well, "kind": "empty", "object_id": None, "display_name": None, "label": None, "order_index": position, "object_snapshot": None} for position, well in enumerate(WELLS)]})
        result[key] = {"layout_key": key, "capacity": min(capacities), "rules": {"imported": True}, "plates": prepared, "warnings": []}
    return result
