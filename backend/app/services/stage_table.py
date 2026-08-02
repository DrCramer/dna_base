from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import String, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import ElectrophoresisControlFile, ElectrophoresisResultFile, Party, RegistryObject, RtResult, StageEvent, StageEventPerformer
from app.schemas import (
    ObjectListItemOut,
    StageTableColumnOut,
    StageTableEventOut,
    StageTableResponse,
    StageTableRowOut,
)
from app.services.no_object import (
    object_decree_no,
    object_description,
    object_external_military_no,
    object_is_no_decree,
    object_is_no_object,
    party_no_decree_controls,
    party_no_object_controls,
)
from app.services.repeats import repeat_sort_suffix
from app.services.stages import stage_summary_for_objects


PUBLIC_STAGE_TO_CANONICAL = {
    "registration": "registration",
    "preparation": "sample_prep",
    "sample_prep": "sample_prep",
    "milling": "milling",
    "extraction": "dna_extraction",
    "dna_extraction": "dna_extraction",
    "realtime": "realtime",
    "pcr": "pcr",
    "electrophoresis": "electrophoresis",
    "analysis": "analysis",
    "all": "all",
}


BASE_OBJECT_COLUMNS = [
    ("rcsme_reg_no", "№ рег РЦСМЭ", "text", False, 130),
    ("no_object", "Нет объекта", "boolean", False, 100),
    ("no_decree", "Нет постановления", "boolean", False, 120),
    ("burnt_bone", "Горелая кость", "boolean", False, 120),
    ("decree_no", "№ постановления", "text", False, 150),
    ("object_type", "Тип", "text", False, 160),
    ("box_no", "Коробка", "text", False, 90),
]


STAGE_COLUMNS: dict[str, list[tuple[str, str, str, bool, int]]] = {
    "registration": [
        ("registry_row_no", "№ п/п", "text", True, 80),
        ("rcsme_reg_no", "№ рег РЦСМЭ", "text", True, 130),
        ("no_object", "Нет объекта", "boolean", False, 100),
        ("no_decree", "Нет постановления", "boolean", False, 120),
        ("decree_no", "№ постановления", "text", True, 150),
        ("external_military_no", "№ присвоенный в в/ч № 522 ЦПООП Северо-Кавказского военного округа, г. Ростов-на-Дону", "text", True, 300),
        ("intake_date", "Дата поступления в РЦСМЭ", "date", True, 150),
        ("decision_date", "Дата постановления", "date", True, 140),
        ("investigator", "Следователь", "text", True, 180),
        ("incoming_no", "№ вх.", "text", True, 100),
        ("box_no", "Коробка", "text", True, 90),
        ("packages_count", "Кол-во пакетов на 1 объект", "number", True, 150),
        ("object_type", "Тип объекта", "text", True, 160),
        ("extracted_before", "Ранее выделяли", "text", True, 150),
        ("not_extracted_before", "Не выделяли ранее", "text", True, 150),
        ("object_description", "Описание / комментарий", "text", True, 260),
    ],
    "sample_prep": [
        ("rcsme_reg_no", "№ рег РЦСМЭ", "text", False, 130),
        ("decree_no", "№ постановления", "text", False, 150),
        ("object_type", "Тип", "text", False, 160),
        ("box_no", "Коробка", "text", False, 90),
        ("object_description", "Описание / комментарий", "text", True, 260),
        ("burnt_bone", "Горелая кость", "boolean", False, 120),
        ("no_biomaterial", "Нет биоматериала", "boolean", False, 140),
        ("external_military_no", "№ присвоенный в в/ч № 522 ЦПООП Северо-Кавказского военного округа, г. Ростов-на-Дону", "text", False, 300),
        ("no_object", "Нет объекта", "boolean", False, 100),
        ("no_decree", "Нет постановления", "boolean", False, 120),
        ("registry_filled_by", "Заполнение реестра", "text", True, 180),
        ("photo_performers", "Фотофиксация", "text", True, 170),
        ("photo_assistants", "Помощь в фотофиксации", "text", True, 180),
        ("washing_performers", "Отмывка", "text", True, 170),
        ("washing_assistants", "Помощь в отмывке", "text", True, 170),
        ("washing_date", "Дата отмывки", "date", True, 130),
        ("bone_tissue_performers", "Размельчение кости / изъятие мягких тканей", "text", True, 260),
        ("bone_tissue_date", "Дата размельчения / изъятия тканей", "date", True, 180),
        ("attempt_no", "Попытка", "number", False, 90),
        ("comment", "Комментарий", "text", True, 220),
    ],
    "milling": [
        *BASE_OBJECT_COLUMNS,
        ("milling_performers", "Размельчение кости на мельнице", "text", True, 230),
        ("cups", "Стаканы", "text", True, 130),
        ("milling_date", "Дата размельчения на мельнице", "date", True, 180),
        ("attempt_no", "Попытка", "number", False, 90),
        ("comment", "Комментарий", "text", True, 220),
    ],
    "dna_extraction": [
        *BASE_OBJECT_COLUMNS,
        ("extraction_date", "Дата получения препарата ДНК", "date", True, 180),
        ("extraction_performers", "Получение препарата ДНК — исполнитель", "text", True, 240),
        ("extraction_method", "Метод получения препарата ДНК", "text", True, 220),
        ("attempt_no", "Попытка", "number", False, 90),
        ("comment", "Комментарий", "text", True, 220),
    ],
    "realtime": [
        *BASE_OBJECT_COLUMNS[:5],
        ("quant_method", "Метод", "text", True, 230),
        ("quant_date", "Дата", "date", True, 190),
        ("quant_performer", "Исполнитель", "text", True, 240),
        ("pipetting_method", "Робот / ручной метод", "text", True, 220),
        ("long_quantity", "Длинная", "number", False, 120),
        ("small_quantity", "Короткая", "number", False, 120),
        ("y_quantity", "Y", "number", False, 90),
        ("comment", "Комментарий", "text", True, 220),
        ("attempt_no", "Попытка", "number", False, 90),
        ("source", "Источник", "text", False, 140),
    ],
    "pcr": [
        *BASE_OBJECT_COLUMNS[:5],
        ("pcr_date", "Дата", "date", True, 150),
        ("locus_panel", "Панель локусов", "text", True, 170),
        ("pipetting_method", "Робот / ручной метод", "text", True, 180),
        ("normalization_performers", "Нормализация PCR — исполнитель", "text", True, 230),
        ("pcr_performers", "Постановка PCR — исполнитель", "text", True, 220),
        ("attempt_no", "Попытка", "number", False, 90),
        ("comment", "Комментарий", "text", True, 220),
    ],
    "electrophoresis": [
        *BASE_OBJECT_COLUMNS[:5],
        ("electrophoresis_date", "Дата", "date", True, 150),
        ("sequencer", "Секвенатор", "text", True, 160),
        ("pipetting_method", "Робот / ручной метод", "text", True, 180),
        ("performer_1", "Исполнитель 1", "text", True, 160),
        ("performer_2", "Исполнитель 2", "text", True, 160),
        ("extra_performers", "Дополнительные исполнители", "text", True, 220),
        ("attempt_no", "Попытка", "number", False, 90),
        ("comment", "Комментарий", "text", True, 220),
    ],
    "analysis": [
        *BASE_OBJECT_COLUMNS[:5],
        ("control_type", "Тип контроля", "text", False, 120),
        ("genotype", "Генотип", "text", True, 170),
        ("analysis_date", "Дата", "date", True, 160),
        ("analysis_performers", "Исполнитель", "text", True, 180),
        ("analysis_status", "Статус анализа", "text", True, 170),
        ("analysis_pdf", "PDF фореза", "text", False, 140),
        ("attempt_no", "Попытка", "number", False, 90),
        ("comment", "Комментарий", "text", True, 220),
    ],
    "all": [
        ("rcsme_reg_no", "№ рег РЦСМЭ", "text", False, 130),
        ("no_object", "Нет объекта", "boolean", False, 100),
        ("no_decree", "Нет постановления", "boolean", False, 120),
        ("burnt_bone", "Горелая кость", "boolean", False, 120),
        ("decree_no", "№ постановления", "text", False, 150),
        ("object_type", "Тип", "text", False, 160),
        ("box_no", "Коробка", "text", False, 90),
        ("sample_prep", "Пробоподготовка", "text", False, 170),
        ("milling", "Измельчение", "text", False, 150),
        ("dna_extraction", "Выделение", "text", False, 150),
        ("realtime", "RealTime", "text", False, 150),
        ("pcr", "ПЦР", "text", False, 130),
        ("electrophoresis", "Электрофорез", "text", False, 170),
        ("analysis", "Анализ", "text", False, 140),
        ("repeat_count", "Повторы", "number", False, 100),
    ],
}


def public_to_canonical(stage_type: str) -> str:
    return PUBLIC_STAGE_TO_CANONICAL.get(stage_type, stage_type)


EMPLOYEE_INPUTS = {
    "registry_filled_by",
    "photo_performers",
    "photo_assistants",
    "washing_performers",
    "washing_assistants",
    "bone_tissue_performers",
    "milling_performers",
    "cups",
    "extraction_performers",
    "quant_performer",
    "normalization_performers",
    "pcr_performers",
    "performer_1",
    "performer_2",
    "extra_performers",
    "analysis_performers",
}


MULTI_EMPLOYEE_INPUTS = {
    "photo_performers",
    "photo_assistants",
    "washing_performers",
    "washing_assistants",
    "bone_tissue_performers",
    "milling_performers",
    "cups",
    "normalization_performers",
    "pcr_performers",
    "extra_performers",
}


DICTIONARY_INPUTS = {
    "extraction_method": "extraction_method",
    "quant_method": "quant_method",
    "pipetting_method": "pipetting_method",
    "locus_panel": "pcr_panel",
    "sequencer": "sequencer",
    "analysis_status": "analysis_status",
}


def _column_input(key: str, kind: str) -> tuple[str, str | None]:
    if key in EMPLOYEE_INPUTS:
        return ("employee_multi" if key in MULTI_EMPLOYEE_INPUTS else "employee", None)
    if key in DICTIONARY_INPUTS:
        return "dictionary", DICTIONARY_INPUTS[key]
    return kind, None


def _columns(stage_type: str) -> list[StageTableColumnOut]:
    columns = []
    for key, label, kind, editable, width in STAGE_COLUMNS.get(stage_type, STAGE_COLUMNS["registration"]):
        input_kind, dictionary_category = _column_input(key, kind)
        columns.append(
            StageTableColumnOut(
                key=key,
                label=label,
                type=kind,
                editable=editable,
                width=width,
                input=input_kind,
                dictionary_category=dictionary_category,
            )
        )
    return columns


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return ", ".join(dict.fromkeys(items)) or None
    text = str(value).strip()
    return text or None


def _is_burnt_bone(description: str | None) -> bool:
    text = (description or "").casefold()
    return "горел" in text and "кость" in text


def _is_no_biomaterial(description: str | None) -> bool:
    return "нет биоматериала" in (description or "").casefold()


def _as_list(value: Any) -> list[str]:
    text = _as_text(value)
    return [item.strip() for item in text.split(",")] if text else []


def _date_value(value: Any) -> Any:
    if isinstance(value, date):
        return value
    return value or None


RT_QUANTITY_KEYS = ("long_quantity", "small_quantity", "y_quantity")
RT_TARGET_BY_QUANTITY_KEY = {
    "long_quantity": "long",
    "small_quantity": "small",
    "y_quantity": "y",
}


def _rt_quantity_value(value: Any) -> Any:
    return None if value in (None, "") else value


def _rt_raw_blank_quantity_keys(raw_json: dict[str, Any] | None) -> set[str]:
    raw = raw_json or {}
    targets = raw.get("targets")
    if not isinstance(targets, dict):
        return set()
    blank_keys: set[str] = set()
    for quantity_key, target_key in RT_TARGET_BY_QUANTITY_KEY.items():
        target_data = targets.get(target_key)
        if isinstance(target_data, dict) and target_data.get("quantity") in (None, ""):
            blank_keys.add(quantity_key)
    return blank_keys


def _mark_rt_import_blanks(values: dict[str, Any], blank_keys: set[str] | None = None) -> None:
    blank_keys = blank_keys or set()
    for key in RT_QUANTITY_KEYS:
        if key in blank_keys or values.get(key) in (None, ""):
            values[key] = "n/a"


def _latest_event(events: list[StageEvent]) -> StageEvent | None:
    active = [event for event in events if not event.is_cancelled]
    if not active:
        return None
    return max(active, key=lambda event: (event.attempt_no or 0, event.event_date or date.min, event.id))


def _event_out(event: StageEvent) -> StageTableEventOut:
    return StageTableEventOut(
        id=event.id,
        stage_type=event.stage_type,
        attempt_no=event.attempt_no,
        event_date=event.event_date,
        source=event.source,
        comment=event.comment,
        performers=[
            item.raw_name
            for item in sorted(event.performers or [], key=lambda performer: performer.order_index)
            if item.raw_name
        ],
    )


def _base_values(
    obj: RegistryObject,
    no_object_control_numbers: set[str] | None = None,
    no_decree_control_numbers: set[str] | None = None,
) -> dict[str, Any]:
    parent = obj.parent_object
    is_repeat = bool(obj.parent_object_id or obj.repeat_suffix)
    description = object_description(obj)
    external_military_no = object_external_military_no(obj)
    return {
        "registry_row_no": obj.registry_row_no,
        "rcsme_reg_no": obj.rcsme_reg_no,
        "decree_no": object_decree_no(obj),
        "external_military_no": external_military_no,
        "intake_date": obj.intake_date or (parent.intake_date if parent else None),
        "decision_date": obj.decision_date or (parent.decision_date if parent else None),
        "investigator": obj.investigator or (parent.investigator if parent else None),
        "incoming_no": obj.incoming_no or (parent.incoming_no if parent else None),
        "box_no": obj.box_no or (parent.box_no if parent else None),
        "packages_count": obj.packages_count if obj.packages_count is not None else (parent.packages_count if parent else None),
        "object_type": obj.object_type or (parent.object_type if parent else None),
        "extracted_before": obj.extracted_before or (parent.extracted_before if parent else None),
        "not_extracted_before": obj.not_extracted_before or (parent.not_extracted_before if parent else None),
        "object_description": description,
        "no_object": object_is_no_object(obj, no_object_control_numbers),
        "no_decree": object_is_no_decree(obj, no_decree_control_numbers),
        "burnt_bone": _is_burnt_bone(description),
        "no_biomaterial": _is_no_biomaterial(description),
        "is_repeat": is_repeat,
        "repeat_suffix": obj.repeat_suffix,
        "parent_rcsme_reg_no": parent.rcsme_reg_no if parent else None,
        "object_repeat_count": len([item for item in obj.repeat_objects if item.status != "archived"]) if not is_repeat else 0,
    }


def _analysis_pdf_values(obj: RegistryObject, event: StageEvent | None) -> dict[str, Any]:
    if not event or event.stage_type != "analysis" or event.source != "electrophoresis_pdf":
        return {}
    file_id = event.raw_json.get("electrophoresis_file_id") if isinstance(event.raw_json, dict) else None
    filename = event.raw_json.get("original_filename") if isinstance(event.raw_json, dict) else None
    if not file_id:
        sample = event.raw_json.get("sample_name_raw") if isinstance(event.raw_json, dict) else None
        for file in obj.electrophoresis_result_files or []:
            raw = file.raw_json or {}
            if filename and raw.get("original_filename") == filename:
                file_id = file.id
                filename = filename or file.filename
                break
            if sample and raw.get("sample_name_raw") == sample:
                file_id = file.id
                filename = filename or file.filename
                break
    if not file_id:
        return {}
    return {
        "analysis_pdf": filename or "PDF",
        "analysis_pdf_file_id": file_id,
        "analysis_pdf_filename": filename or "PDF",
    }


def _control_object_out(control: ElectrophoresisControlFile) -> ObjectListItemOut:
    now = control.created_at or datetime.now()
    return ObjectListItemOut(
        id=-control.id,
        party_id=control.party_id,
        party_no=None,
        case_year=control.case_year,
        parent_object_id=None,
        repeat_suffix=None,
        registry_row_no=None,
        intake_date=None,
        decision_date=None,
        investigator=None,
        incoming_no=None,
        decree_no=None,
        object_description=None,
        external_military_no=None,
        extraction_note=None,
        box_no=None,
        packages_count=None,
        rcsme_reg_no="Контроль",
        rcsme_reg_no_is_manual=False,
        object_type=None,
        extracted_before=None,
        not_extracted_before=None,
        registry_filled_by=None,
        status="active",
        source_import_batch_id=None,
        source_sheet_name=None,
        source_row_number=None,
        decree_no_base=None,
        rcsme_reg_no_base=None,
        stage_summary={},
        last_stage="analysis",
        last_stage_date=control.analysis_date,
        repeat_count=0,
        raw_registry_json={},
        created_at=now,
        updated_at=control.updated_at or now,
    )


def _control_row(control: ElectrophoresisControlFile) -> StageTableRowOut:
    label = control.control_label or control.control_type
    values = {
        "rcsme_reg_no": "Контроль",
        "decree_no": None,
        "object_type": None,
        "box_no": None,
        "no_object": False,
        "no_decree": False,
        "burnt_bone": False,
        "control_type": label,
        "analysis_date": control.analysis_date.isoformat() if control.analysis_date else None,
        "analysis_performers": control.analysis_performer,
        "analysis_status": "Контроль",
        "analysis_pdf": control.filename or "PDF",
        "analysis_pdf_file_id": f"control-{control.id}",
        "analysis_pdf_filename": control.filename or "PDF",
        "attempt_no": None,
        "comment": None,
        "is_control_row": True,
        "control_file_id": control.id,
        "stage_attempt_key": f"control:{control.id}",
    }
    return StageTableRowOut(
        object=_control_object_out(control),
        values=values,
        latest_event=None,
        attempt_no=None,
        repeat_count=0,
        history_available=False,
        history=[],
    )


def _control_matches_query(control: ElectrophoresisControlFile, q: str | None) -> bool:
    if not q:
        return True
    needle = q.lower()
    haystack = " ".join(str(value or "") for value in (
        "Контроль",
        control.control_type,
        control.control_label,
        control.filename,
        control.analysis_performer,
    )).lower()
    return needle in haystack


def _stage_values(
    stage_type: str,
    obj: RegistryObject,
    latest: StageEvent | None,
    summaries: dict[str, Any],
    no_object_control_numbers: set[str] | None = None,
    no_decree_control_numbers: set[str] | None = None,
) -> dict[str, Any]:
    values = _base_values(obj, no_object_control_numbers, no_decree_control_numbers)
    if stage_type == "registration":
        return values
    if stage_type == "all":
        stage_summary = summaries.get("stage_summary", {})
        values.update(
            {
                "sample_prep": _stage_chip(stage_summary.get("sample_prep")),
                "milling": _stage_chip(stage_summary.get("milling")),
                "dna_extraction": _stage_chip(stage_summary.get("dna_extraction")),
                "realtime": _stage_chip(stage_summary.get("realtime")),
                "pcr": _stage_chip(stage_summary.get("pcr")),
                "electrophoresis": _stage_chip(stage_summary.get("electrophoresis")),
                "analysis": _stage_chip(stage_summary.get("analysis")),
                "repeat_count": summaries.get("repeat_count", 0),
            }
        )
        return values
    if not latest:
        if stage_type == "realtime":
            rt = _latest_rt(obj)
            if rt:
                values.update({"quant_method": rt.target, "source": "rt_import"})
                quantity_key = _rt_quantity_key(rt.target)
                if quantity_key:
                    values[quantity_key] = _rt_quantity_value(rt.quantity_ng_ul if rt.quantity_ng_ul is not None else rt.mean_quantity_ng_ul)
                _mark_rt_import_blanks(values)
        return values
    values.update(
        {
            "attempt_no": latest.attempt_no,
            "comment": latest.comment,
            "source": latest.source,
        }
    )
    if stage_type == "sample_prep" and latest.sample_prep_detail:
        detail = latest.sample_prep_detail
        values.update(
            {
                "registry_filled_by": detail.registry_filled_by,
                "photo_performers": _as_text(detail.photo_performers),
                "photo_assistants": _as_text(detail.photo_assistants),
                "washing_performers": _as_text(detail.washing_performers),
                "washing_assistants": _as_text(detail.washing_assistants),
                "washing_date": _date_value(detail.washing_date),
                "bone_tissue_performers": _as_text(detail.bone_tissue_performers),
                "bone_tissue_date": _date_value(detail.bone_tissue_date),
            }
        )
    elif stage_type == "milling" and latest.milling_detail:
        detail = latest.milling_detail
        values.update(
            {
                "milling_performers": _as_text(detail.milling_performers),
                "cups": detail.cups,
                "milling_date": _date_value(detail.milling_date),
            }
        )
    elif stage_type == "dna_extraction" and latest.dna_extraction_detail:
        detail = latest.dna_extraction_detail
        values.update(
            {
                "extraction_date": _date_value(detail.extraction_date),
                "extraction_performers": _as_text([item.raw_name for item in latest.performers if item.raw_name]),
                "extraction_method": detail.extraction_method,
            }
        )
    elif stage_type == "realtime":
        detail = latest.realtime_detail
        rt = _latest_rt(obj)
        raw_blank_keys = _rt_raw_blank_quantity_keys(latest.raw_json if latest.source == "rt_import" else None)
        if detail:
            values.update(
                {
                    "quant_method": detail.quant_method,
                    "quant_date": _date_value(detail.quant_date),
                    "quant_performer": detail.quant_performer,
                    "pipetting_method": detail.pipetting_method,
                    "concentration": detail.concentration,
                    "ct_cq": detail.ct_cq,
                    "di": detail.di,
                    "ipc": detail.ipc,
                    "long_quantity": detail.long_quantity,
                    "small_quantity": detail.small_quantity,
                    "y_quantity": detail.y_quantity,
                    "comment": detail.comment or latest.comment,
                }
            )
        if rt:
            quantity_key = _rt_quantity_key(rt.target)
            if quantity_key and values.get(quantity_key) in (None, ""):
                values[quantity_key] = _rt_quantity_value(rt.quantity_ng_ul if rt.quantity_ng_ul is not None else rt.mean_quantity_ng_ul)
        if latest.source == "rt_import" or rt:
            _mark_rt_import_blanks(values, raw_blank_keys)
    elif stage_type == "pcr" and latest.pcr_detail:
        detail = latest.pcr_detail
        values.update(
            {
                "pcr_date": _date_value(detail.pcr_date),
                "locus_panel": detail.locus_panel,
                "pipetting_method": detail.pipetting_method,
                "normalization_performers": _as_text(detail.normalization_performers),
                "pcr_performers": _as_text(detail.pcr_performers),
            }
        )
    elif stage_type == "electrophoresis" and latest.electrophoresis_detail:
        detail = latest.electrophoresis_detail
        performers = _as_list(detail.performers)
        values.update(
            {
                "electrophoresis_date": _date_value(detail.electrophoresis_date),
                "sequencer": detail.sequencer,
                "pipetting_method": detail.pipetting_method,
                "performer_1": performers[0] if len(performers) > 0 else None,
                "performer_2": performers[1] if len(performers) > 1 else None,
                "extra_performers": ", ".join(performers[2:]) if len(performers) > 2 else None,
            }
        )
    elif stage_type == "analysis" and latest.analysis_detail:
        detail = latest.analysis_detail
        values.update(
            {
                "genotype": detail.genotype,
                "analysis_date": _date_value(detail.analysis_date),
                "analysis_performers": _as_text([item.raw_name for item in latest.performers if item.raw_name]),
                "analysis_status": detail.status,
            }
        )
        values.update(_analysis_pdf_values(obj, latest))
    return values


def _stage_chip(summary: dict[str, Any] | None) -> str | None:
    if not summary:
        return None
    count = summary.get("count") or 0
    latest_date = summary.get("latest_date")
    suffix = f" · {latest_date}" if latest_date else ""
    return f"{count}{suffix}"


def _latest_rt(obj: RegistryObject) -> RtResult | None:
    results = [item for item in obj.rt_results or [] if item.object_id == obj.id]
    if not results:
        return None
    return max(results, key=lambda item: item.id)


def _rt_quantity_key(target: str | None) -> str | None:
    text = (target or "").lower()
    if "ipc" in text:
        return None
    if "large" in text or "long" in text:
        return "long_quantity"
    if "small" in text or "short" in text:
        return "small_quantity"
    if text.strip() in {"y", "t.y", "ty"} or text.strip().endswith(".y"):
        return "y_quantity"
    return None


def _object_options():
    return (
        selectinload(RegistryObject.parent_object),
        selectinload(RegistryObject.repeat_objects),
        selectinload(RegistryObject.rt_results),
        selectinload(RegistryObject.electrophoresis_result_files),
        selectinload(RegistryObject.stage_events).selectinload(StageEvent.performers),
        selectinload(RegistryObject.stage_events).selectinload(StageEvent.sample_prep_detail),
        selectinload(RegistryObject.stage_events).selectinload(StageEvent.milling_detail),
        selectinload(RegistryObject.stage_events).selectinload(StageEvent.dna_extraction_detail),
        selectinload(RegistryObject.stage_events).selectinload(StageEvent.realtime_detail),
        selectinload(RegistryObject.stage_events).selectinload(StageEvent.pcr_detail),
        selectinload(RegistryObject.stage_events).selectinload(StageEvent.electrophoresis_detail),
        selectinload(RegistryObject.stage_events).selectinload(StageEvent.analysis_detail),
    )


def _number_text_base(value: str | None) -> str | None:
    if not value:
        return None
    digits = ""
    for char in value:
        if char.isdigit():
            digits += char
        elif digits:
            break
    return digits or None


def _object_sort_key(obj: RegistryObject) -> tuple[Any, ...]:
    root = obj.parent_object or obj
    root_base = root.rcsme_reg_no_base or _number_text_base(root.rcsme_reg_no)
    try:
        root_number = int(root_base) if root_base else 10**12
    except ValueError:
        root_number = 10**12
    is_repeat = bool(obj.parent_object_id or obj.repeat_suffix)
    return (
        root_number,
        root.rcsme_reg_no or "",
        1 if is_repeat else 0,
        *repeat_sort_suffix(obj.repeat_suffix),
        obj.rcsme_reg_no or "",
        obj.id,
    )


def _query_condition(q: str):
    needle = f"%{q.strip()}%"
    stage_match = select(StageEvent.object_id).outerjoin(StageEventPerformer).where(
        or_(
            StageEvent.comment.ilike(needle),
            StageEvent.source.ilike(needle),
            StageEvent.raw_json.cast(String).ilike(needle),
            StageEventPerformer.raw_name.ilike(needle),
        )
    )
    rt_match = select(RtResult.object_id).where(
        or_(
            RtResult.sample_name_raw.ilike(needle),
            RtResult.normalized_sample_name.ilike(needle),
            RtResult.target.ilike(needle),
            RtResult.result_flag.ilike(needle),
            RtResult.raw_json.cast(String).ilike(needle),
        )
    )
    return or_(
        RegistryObject.rcsme_reg_no.ilike(needle),
        RegistryObject.decree_no.ilike(needle),
        RegistryObject.external_military_no.ilike(needle),
        RegistryObject.object_description.ilike(needle),
        RegistryObject.object_type.ilike(needle),
        RegistryObject.investigator.ilike(needle),
        RegistryObject.incoming_no.ilike(needle),
        RegistryObject.box_no.ilike(needle),
        RegistryObject.id.in_(stage_match),
        RegistryObject.id.in_(rt_match),
    )


def _passes_filter(row: StageTableRowOut, filters: dict[str, Any], stage_type: str) -> bool:
    quick = filters.get("quick")
    has_stage_data = row.latest_event is not None
    if stage_type == "realtime" and any(row.values.get(key) not in (None, "") for key in ("long_quantity", "small_quantity", "y_quantity", "quant_method")):
        has_stage_data = True
    if quick == "empty" and has_stage_data:
        return False
    if quick == "filled" and not has_stage_data:
        return False
    if quick == "repeat" and row.repeat_count <= 0:
        return False
    if filters.get("box_no") and row.object.box_no != filters["box_no"]:
        return False
    if filters.get("object_type") and row.object.object_type != filters["object_type"]:
        return False
    if filters.get("needs_repeat"):
        status = str(row.values.get("analysis_status") or "").lower()
        if stage_type != "analysis" or "повтор" not in status:
            return False
    return True


async def select_stage_table_objects(
    session: AsyncSession,
    *,
    party_ids: list[int],
    q: str | None = None,
    include_archived: bool = False,
) -> list[RegistryObject]:
    stmt = select(RegistryObject).options(*_object_options())
    conditions = []
    if party_ids:
        conditions.append(RegistryObject.party_id.in_(party_ids))
    if q:
        conditions.append(_query_condition(q))
    if not include_archived:
        active_parties = select(Party.id).where(Party.status != "archived")
        conditions.append(RegistryObject.party_id.in_(active_parties))
        conditions.append(RegistryObject.status != "archived")
    for condition in conditions:
        stmt = stmt.where(condition)
    stmt = stmt.order_by(RegistryObject.id.asc())
    result = await session.execute(stmt)
    return sorted(list(result.scalars().unique().all()), key=_object_sort_key)


async def build_stage_table(
    session: AsyncSession,
    *,
    party_ids: list[int],
    stage_type: str,
    q: str | None = None,
    filters: dict[str, Any] | None = None,
    include_archived: bool = False,
    show_history: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> StageTableResponse:
    canonical_stage = public_to_canonical(stage_type)
    filters = filters or {}
    objects = await select_stage_table_objects(
        session,
        party_ids=party_ids,
        q=q,
        include_archived=include_archived,
    )
    no_object_controls = await party_no_object_controls(session, party_ids)
    no_decree_controls = await party_no_decree_controls(session, party_ids)
    summaries = await stage_summary_for_objects(session, [item.id for item in objects])
    rows: list[StageTableRowOut] = []
    for obj in objects:
        no_object_control_numbers = no_object_controls.get(obj.party_id or 0, set())
        no_decree_control_numbers = no_decree_controls.get(obj.party_id or 0, set())
        object_summaries = summaries.get(obj.id, {})
        stage_events = [] if canonical_stage in ("registration", "all") else [
            event
            for event in obj.stage_events
            if event.stage_type == canonical_stage and not event.is_cancelled
        ]
        history = [_event_out(event) for event in sorted(stage_events, key=lambda item: item.attempt_no)]
        data = ObjectListItemOut.model_validate(obj).model_dump()
        data.update(object_summaries)
        object_out = ObjectListItemOut(**data)
        if canonical_stage == "analysis" and stage_events:
            sorted_events = sorted(stage_events, key=lambda item: item.attempt_no)
            attempt_count = len(sorted_events)
            for index, event in enumerate(sorted_events):
                values = _stage_values(canonical_stage, obj, event, object_summaries, no_object_control_numbers, no_decree_control_numbers)
                values.update(
                    {
                        "is_stage_attempt_repeat": event.attempt_no > 1,
                        "stage_attempt_count": attempt_count if index == 0 else None,
                        "stage_attempt_parent_object_id": obj.id,
                        "stage_attempt_key": f"{obj.id}:analysis:{event.attempt_no}",
                    }
                )
                row = StageTableRowOut(
                    object=object_out,
                    values=values,
                    latest_event=_event_out(event),
                    attempt_no=event.attempt_no,
                    repeat_count=max(attempt_count - 1, 0) if index == 0 else 0,
                    history_available=attempt_count > 1 and index == 0,
                    history=history if show_history and index == 0 else [],
                )
                if _passes_filter(row, filters, canonical_stage):
                    rows.append(row)
            continue

        latest = _latest_event(stage_events)
        repeat_count = max(len(stage_events) - 1, 0)
        values = _stage_values(canonical_stage, obj, latest, object_summaries, no_object_control_numbers, no_decree_control_numbers)
        if canonical_stage == "analysis":
            values.update(
                {
                    "is_stage_attempt_repeat": False,
                    "stage_attempt_count": 0,
                    "stage_attempt_parent_object_id": obj.id,
                    "stage_attempt_key": f"{obj.id}:analysis:empty",
                }
            )
        row = StageTableRowOut(
            object=object_out,
            values=values,
            latest_event=_event_out(latest) if latest else None,
            attempt_no=latest.attempt_no if latest else None,
            repeat_count=repeat_count if canonical_stage not in ("registration", "all") else object_summaries.get("repeat_count", 0),
            history_available=len(stage_events) > 1,
            history=history if show_history else [],
        )
        if _passes_filter(row, filters, canonical_stage):
            rows.append(row)
    if canonical_stage == "analysis":
        control_result = await session.execute(
            select(ElectrophoresisControlFile)
            .where(ElectrophoresisControlFile.party_id.in_(party_ids))
            .order_by(ElectrophoresisControlFile.party_id, ElectrophoresisControlFile.control_type, ElectrophoresisControlFile.id)
        )
        for control in control_result.scalars().all():
            if not _control_matches_query(control, q):
                continue
            row = _control_row(control)
            if _passes_filter(row, filters, canonical_stage):
                rows.append(row)
    total = len(rows)
    paged_rows = rows[offset : offset + limit] if limit is not None else rows[offset:]
    return StageTableResponse(
        stage_type=canonical_stage,
        party_ids=party_ids,
        columns=_columns(canonical_stage),
        rows=paged_rows,
        total=total,
        filters=filters,
    )
