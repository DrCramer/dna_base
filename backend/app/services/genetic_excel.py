from typing import Any
from fastapi import HTTPException
from app.parsers.genetic_identity import genetic_key
from app.schemas.genetic_protocols import GeneticExcelApply, GeneticNumberInput


def excel_source_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    layouts = data.get("layouts") or {}
    primary = "source" if any(cell.get("kind") == "sample" for cell in layouts.get("source", [])) else "pcr"
    items = [{"raw_name": cell["sample_name_raw"], "source_key": f"{primary}:{cell['plate_index']}:{cell['well']}"} for cell in layouts.get(primary, []) if cell.get("kind") == "sample"]
    keys = {genetic_key(item["raw_name"]) for item in items}
    for key, cells in layouts.items():
        if key == primary:
            continue
        for cell in cells:
            if cell.get("kind") == "sample" and genetic_key(cell["sample_name_raw"]) not in keys:
                items.append({"raw_name": cell["sample_name_raw"], "source_key": f"{key}:{cell['plate_index']}:{cell['well']}"})
                keys.add(genetic_key(cell["sample_name_raw"]))
    if not items:
        items = [{"raw_name": obj["sample_name_raw"], "source_key": f"input:{index}"} for index, obj in enumerate(data.get("objects", []))]
    if len({item["source_key"] for item in items}) != len(items):
        raise HTTPException(status_code=400, detail="В Excel повторяются координаты лунок. Исправьте подписи строк плашки.")
    return items


def resolve_excel_items(payload: GeneticExcelApply, data: dict[str, Any]) -> list[GeneticNumberInput]:
    source_items = excel_source_items(data)
    by_source = {item["source_key"]: item for item in source_items}
    result = []
    for item in payload.items:
        if item.source_key:
            source = by_source.get(item.source_key)
        else:
            matches = [entry for entry in source_items if genetic_key(entry["raw_name"]) == genetic_key(item.raw_name)]
            source = matches[0] if len(matches) == 1 else None
        if source is None:
            raise HTTPException(status_code=400, detail="Не удалось однозначно сопоставить объект с исходной строкой Excel")
        result.append(item.model_copy(update={"source_key": source["source_key"]}))
    if len({item.source_key for item in result}) != len(result):
        raise HTTPException(status_code=400, detail="Одна исходная строка Excel указана несколько раз")
    return result


def excel_cells(payload: GeneticExcelApply, data: dict[str, Any], items: list[GeneticNumberInput], object_ids: list[int]) -> list[dict[str, Any]]:
    by_source = dict(zip([item.source_key for item in items], object_ids))
    original = excel_source_items(data)
    keys_by_name: dict[str, list[str]] = {}
    for item in original:
        keys_by_name.setdefault(genetic_key(item["raw_name"]), []).append(item["source_key"])
    file_coordinates = {f"{key}:{cell['plate_index']}:{cell['well']}" for key, cells in data.get("layouts", {}).items() for cell in cells}
    if set(payload.well_mappings) - file_coordinates:
        raise HTTPException(status_code=400, detail="Сопоставление содержит координату вне исходного Excel")
    cells = []
    for layout_key, layout in data.get("layouts", {}).items():
        for cell in layout:
            coordinate = f"{layout_key}:{cell['plate_index']}:{cell['well']}"
            object_id = None
            if cell["kind"] == "sample":
                candidates = keys_by_name.get(genetic_key(cell["sample_name_raw"]), [])
                source_key = payload.well_mappings.get(coordinate) or (coordinate if coordinate in by_source else candidates[0] if len(candidates) == 1 else None)
                if source_key is None:
                    raise HTTPException(status_code=400, detail=f"Уточните объект в лунке {cell['well']} плашки {cell['plate_index']} ({layout_key})")
                object_id = by_source.get(source_key)
                if object_id is None:
                    if source_key not in {entry["source_key"] for entry in original}:
                        raise HTTPException(status_code=400, detail="Лунка ссылается на неизвестный исходный объект")
                    continue
            cells.append({"layout_key": layout_key, "plate_index": cell["plate_index"], "well": cell["well"], "kind": cell["kind"], "source_id": object_id, "label": cell["sample_name_raw"] if cell["kind"] != "sample" else None})
    return cells


def selected_stage_patch(stage: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    groups = {"date": ("work_date",), "kit": ("profile_id", "kit_name"), "performers": ("performer_ids", "performers"), "sequencer": ("sequencer_name",), "comment": ("comment",)}
    result = {"stage_type": stage["stage_type"], "settings": stage["settings"]}
    for field in fields:
        keys = groups[field]
        if any(stage.get(key) is not None and stage.get(key) != [] for key in keys):
            result.update({key: stage.get(key) for key in keys})
    return result
