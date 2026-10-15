import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GeneticExamination, GeneticExaminationObject, GeneticExaminationRtResult, GeneticExaminationRtRun
from app.parsers.genetic_identity import genetic_key, genetic_number_parts, control_kind
from app.parsers.rt import aggregate_rt_rows, round_rt_quantity
from app.schemas.genetic_protocols import GeneticNumbersRequest, GeneticRtCommit
from app.services.protocol_plate import natural_key
from app.services.protocol_resources import validate_protocol_size


def number_rows(payload: GeneticNumbersRequest) -> list[dict[str, Any]]:
    validate_protocol_size(list(range(len(payload.items))))
    rows = []
    identities: dict[tuple[str, str], int] = {}
    for index, item in enumerate(payload.items):
        examination_no, object_index = genetic_number_parts(item.raw_name, item.examination_no)
        key = genetic_key(item.raw_name)
        exam_key = genetic_key(examination_no)
        error = None
        if not key or any(ord(character) < 32 for character in key + exam_key):
            error = "Пустой номер или недопустимые управляющие символы"
        elif len(key) > 255 or len(exam_key) > 120:
            error = "Нормализованный номер превышает допустимую длину"
        elif control_kind(item.raw_name):
            error = "Контрольная проба не является объектом экспертизы"
        elif not examination_no:
            error = "Укажите номер экспертизы"
        elif not exam_key:
            error = "Пустой номер экспертизы"
        elif (exam_key, key) in identities:
            error = "Повтор имени в списке: укажите различающий идентификатор"
            rows[identities[(exam_key, key)]]["error"] = error
        else:
            identities[(exam_key, key)] = index
        rows.append({"raw_name": item.raw_name, "source_key": item.source_key, "normalized_name": key, "examination_no": examination_no, "object_index": object_index, "examination_year": payload.examination_year, "description": item.description, "error": error})
    return rows


async def preview_numbers(session: AsyncSession, payload: GeneticNumbersRequest) -> dict[str, Any]:
    rows = number_rows(payload)
    exams = {exam.normalized_examination_no: exam for exam in (await session.execute(select(GeneticExamination).where(GeneticExamination.examination_year == payload.examination_year, GeneticExamination.normalized_examination_no.in_({genetic_key(row["examination_no"]) for row in rows})))).scalars()}
    existing = {(obj.examination_id, obj.object_no_normalized): obj for obj in (await session.execute(select(GeneticExaminationObject).where(GeneticExaminationObject.examination_id.in_([exam.id for exam in exams.values()]), GeneticExaminationObject.object_no_normalized.in_([row["normalized_name"] for row in rows])))).scalars()} if exams else {}
    for row in rows:
        exam = exams.get(genetic_key(row["examination_no"]))
        obj = existing.get((exam.id, row["normalized_name"])) if exam else None
        row["existing"] = obj is not None
    return {"items": rows, "added": sum(not row["existing"] and not row["error"] for row in rows), "existing": sum(row["existing"] and not row["error"] for row in rows), "unresolved": sum(bool(row["error"]) for row in rows)}


async def apply_numbers(session: AsyncSession, payload: GeneticNumbersRequest, user_id: int) -> dict[str, Any]:
    preview = await preview_numbers(session, payload)
    if preview["unresolved"]:
        raise HTTPException(status_code=400, detail="Исправьте конфликты и укажите экспертизы для всех объектов")
    ids = []
    added = 0
    # Стабильный порядок блокировок при одновременной вставке нескольких экспертиз.
    exam_ids = {}
    for row in sorted(preview["items"], key=lambda item: genetic_key(item["examination_no"])):
        key = genetic_key(row["examination_no"])
        if key in exam_ids:
            continue
        await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"genetic:{payload.examination_year}:{key}"))))
        exam_id = (await session.execute(insert(GeneticExamination).values(examination_year=payload.examination_year, examination_no=row["examination_no"], normalized_examination_no=key, created_by_user_id=user_id).on_conflict_do_nothing(index_elements=["examination_year", "normalized_examination_no"]).returning(GeneticExamination.id))).scalar_one_or_none()
        if exam_id is None:
            exam_id = (await session.execute(select(GeneticExamination.id).where(GeneticExamination.examination_year == payload.examination_year, GeneticExamination.normalized_examination_no == key))).scalar_one()
        exam_ids[key] = exam_id
    next_order = {exam_id: int((await session.execute(select(func.max(GeneticExaminationObject.order_index)).where(GeneticExaminationObject.examination_id == exam_id))).scalar_one_or_none() or 0) + 1 for exam_id in exam_ids.values()}
    for row in preview["items"]:
        exam_id = exam_ids[genetic_key(row["examination_no"])]
        obj_id = (await session.execute(insert(GeneticExaminationObject).values(examination_id=exam_id, object_no_raw=row["raw_name"], object_no_normalized=row["normalized_name"], object_index=row["object_index"], display_name=row["raw_name"], description=row["description"], order_index=next_order[exam_id]).on_conflict_do_nothing(index_elements=["examination_id", "object_no_normalized"]).returning(GeneticExaminationObject.id))).scalar_one_or_none()
        if obj_id is None:
            obj_id = (await session.execute(select(GeneticExaminationObject.id).where(GeneticExaminationObject.examination_id == exam_id, GeneticExaminationObject.object_no_normalized == row["normalized_name"]))).scalar_one()
        else:
            next_order[exam_id] += 1
            added += 1
        ids.append(obj_id)
    preview["objects"] = await genetic_object_snapshots(session, ids, payload.examination_year)
    preview["object_ids"] = ids
    preview["added"], preview["existing"] = added, len(ids) - added
    return preview


async def genetic_object_snapshots(session: AsyncSession, object_ids: list[int], year: int) -> list[dict[str, Any]]:
    validate_protocol_size(object_ids)
    rows = (await session.execute(select(GeneticExaminationObject, GeneticExamination).join(GeneticExamination, GeneticExamination.id == GeneticExaminationObject.examination_id).where(GeneticExaminationObject.id.in_(set(object_ids)), GeneticExamination.examination_year == year))).all()
    if len(rows) != len(set(object_ids)):
        raise HTTPException(status_code=400, detail="Объекты не найдены в выбранном году экспертизы")
    # Последняя целая попытка выбирается в БД без загрузки всей истории мишеней.
    latest_runs = (select(GeneticExaminationRtResult.genetic_examination_object_id.label("object_id"), GeneticExaminationRtRun.id.label("run_id"))
        .join(GeneticExaminationRtRun, GeneticExaminationRtRun.id == GeneticExaminationRtResult.run_id)
        .where(GeneticExaminationRtResult.genetic_examination_object_id.in_(object_ids), GeneticExaminationRtResult.is_current.is_(True), GeneticExaminationRtRun.active.is_(True), GeneticExaminationRtRun.examination_year == year)
        .distinct(GeneticExaminationRtResult.genetic_examination_object_id)
        .order_by(GeneticExaminationRtResult.genetic_examination_object_id, GeneticExaminationRtRun.imported_at.desc(), GeneticExaminationRtRun.id.desc()).subquery())
    results = (await session.execute(select(GeneticExaminationRtResult, GeneticExaminationRtRun)
        .join(GeneticExaminationRtRun, GeneticExaminationRtRun.id == GeneticExaminationRtResult.run_id)
        .join(latest_runs, (latest_runs.c.object_id == GeneticExaminationRtResult.genetic_examination_object_id) & (latest_runs.c.run_id == GeneticExaminationRtResult.run_id))
        .where(GeneticExaminationRtResult.is_current.is_(True)).order_by(GeneticExaminationRtResult.id.desc()))).all() if object_ids else []
    rt_by_object: dict[int, dict[str, Any]] = {}
    for result, run in results:
        rt = rt_by_object.setdefault(result.genetic_examination_object_id, {"run_id": run.id, "source_filename": run.source_filename, "run_date": run.run_date.isoformat() if run.run_date else None, "long_quantity": None, "small_quantity": None, "y_quantity": None, "ct_cq": None, "di": None, "targets": {}})
        if rt["run_id"] != run.id or result.target_key in rt["targets"]:
            continue
        quantity = round_rt_quantity(result.quantity)
        rt["targets"][result.target_key] = {"result_id": result.id, "quantity": quantity, "ct_cq": result.ct_cq, "well": result.well, "sample_name_raw": result.sample_name_raw}
        if result.target_key in {"long", "small", "y"}:
            rt[f"{result.target_key}_quantity"] = quantity
        if result.target_key == "small":
            rt["ct_cq"], rt["di"] = result.ct_cq, result.di
    output = []
    for obj, exam in rows:
        rt = rt_by_object.get(obj.id)
        if rt:
            rt["concentration"] = rt["small_quantity"]
        output.append({"id": obj.id, "source_id": obj.id, "source_kind": "genetic_examination", "display_name": obj.display_name, "object_no_raw": obj.object_no_raw, "object_no_normalized": obj.object_no_normalized, "object_index": obj.object_index, "description": obj.description, "examination_id": exam.id, "examination_year": exam.examination_year, "examination_no": exam.examination_no, "rt": rt})
    return sorted(output, key=lambda item: (natural_key(item["display_name"]), item["id"]))


def match_genetic_sample(sample_key: str, objects: list[dict[str, Any]]) -> tuple[str, int | None, list[int]]:
    exact = [obj["id"] for obj in objects if obj["object_no_normalized"] == sample_key]
    candidates = exact or [obj["id"] for obj in objects if obj["object_no_normalized"].replace("/", "_") == sample_key.replace("/", "_")]
    return ("matched", candidates[0], candidates) if len(candidates) == 1 else ("ambiguous" if candidates else "unmatched", None, candidates)


def rt_samples(rows: list[dict[str, Any]], objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    samples = aggregate_rt_rows(rows, policy="genetic")
    for item in samples:
        status, obj_id, candidates = match_genetic_sample(item["normalized_sample_name"], objects)
        item.update(status=status, object_id=obj_id, candidate_ids=candidates)
    return samples


def finite_quantity(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


async def commit_rt(session: AsyncSession, payload: GeneticRtCommit, uploads: list[Any], user_id: int) -> dict[str, Any]:
    objects = await genetic_object_snapshots(session, payload.object_ids, payload.examination_year)
    allowed_ids = {obj["id"] for obj in objects}
    mappings = {(mapping.upload_id, mapping.sample_key): mapping.object_id for mapping in payload.mappings}
    upload_ids = {upload.id for upload in uploads}
    if any(mapping.upload_id not in upload_ids for mapping in payload.mappings) or any(item.upload_id not in upload_ids for item in payload.excluded_samples):
        raise HTTPException(status_code=400, detail="Сопоставление относится к файлу вне текущего импорта")
    if len({upload.sha256 for upload in uploads}) != len(uploads) and not payload.confirm_duplicate:
        raise HTTPException(status_code=409, detail="В задании повторяется содержимое RT-файла. Подтвердите повторный импорт.")
    if any(obj_id not in allowed_ids for obj_id in mappings.values()):
        raise HTTPException(status_code=400, detail="Сопоставление содержит объект вне выбранной экспертизы/года")
    plans = []
    for upload in sorted(uploads, key=lambda item: item.sha256):
        await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"genetic-rt:{payload.examination_year}:{upload.sha256}"))))
    for upload in uploads:
        valid_keys = {sample["normalized_sample_name"] for sample in rt_samples(upload.parsed_json["rows"], objects)}
        if any(key not in valid_keys for (upload_id, key) in mappings if upload_id == upload.id):
            raise HTTPException(status_code=400, detail="Образец отсутствует в подтверждаемом RT-файле")
        duplicate = (await session.execute(select(GeneticExaminationRtRun.id).where(GeneticExaminationRtRun.sha256 == upload.sha256, GeneticExaminationRtRun.examination_year == payload.examination_year))).first()
        if duplicate and not payload.confirm_duplicate:
            raise HTTPException(status_code=409, detail="Файл уже импортирован. Подтвердите повторную загрузку.")
        matched = {item["normalized_sample_name"]: item["object_id"] for item in rt_samples(upload.parsed_json["rows"], objects) if item["object_id"]}
        matched.update({key: obj_id for (file_id, key), obj_id in mappings.items() if file_id == upload.id})
        for item in payload.excluded_samples:
            if item.upload_id == upload.id:
                matched.pop(item.sample_key, None)
        values = []
        quantities: dict[tuple[int, str], float | None] = {}
        for row in upload.parsed_json["rows"]:
            key = genetic_key(row.get("sample_name_raw"))
            object_id = matched.get(key)
            if not object_id:
                continue
            target = row.get("target_key") or "other"
            quantity = finite_quantity(row.get("quantity_ng_ul") if row.get("quantity_ng_ul") is not None else row.get("mean_quantity_ng_ul"))
            pair = (object_id, target)
            if target in {"long", "small", "y"} and pair in quantities and quantities[pair] != quantity:
                raise HTTPException(status_code=400, detail=f"В файле {upload.source_filename} несколько разных значений одной мишени образца {row.get('sample_name_raw')}. Требуется уточнение исходного файла.")
            quantities[pair] = quantity
            values.append({"genetic_examination_object_id": object_id, "sample_name_raw": row["sample_name_raw"], "normalized_sample_name": key, "target_key": target, "quantity": quantity, "ct_cq": finite_quantity(row.get("ct")), "di": finite_quantity(row.get("degradation_index")), "well": row.get("well"), "raw_json": row})
        if not values:
            raise HTTPException(status_code=400, detail=f"В файле {upload.source_filename} не выбрано ни одного совпавшего образца")
        plans.append((upload, values))
    affected = {value["genetic_examination_object_id"] for _, values in plans for value in values}
    if payload.mode == "replace":
        await session.execute(update(GeneticExaminationRtResult).where(GeneticExaminationRtResult.genetic_examination_object_id.in_(affected)).values(is_current=False))
    run_ids = []
    for upload, values in plans:
        data = upload.parsed_json
        run = GeneticExaminationRtRun(examination_year=payload.examination_year, source_filename=upload.source_filename, sha256=upload.sha256, run_date=datetime.fromisoformat(data["run_date"]).date() if data.get("run_date") else None, quant_method=data.get("quant_method"), imported_by_user_id=user_id, metadata_json={"mode": payload.mode, "upload_id": upload.id})
        session.add(run)
        await session.flush()
        for value in values:
            session.add(GeneticExaminationRtResult(run_id=run.id, **value))
        run_ids.append(run.id)
    await session.flush()
    return {"run_ids": run_ids, "matched": len(affected), "objects": await genetic_object_snapshots(session, payload.object_ids, payload.examination_year)}
