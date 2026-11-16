from sqlalchemy import and_, case, cast, column, distinct, func, literal, select
from sqlalchemy.dialects.postgresql import JSONB, aggregate_order_by

from app.models import LabProtocol


def protocol_summary_statement():
    """Компактная сводка в PostgreSQL без загрузки плашек и RT в Python."""
    empty = cast(literal("[]"), JSONB)

    def elements(key):
        value = cast(LabProtocol.snapshot_json[key], JSONB)
        array = case((func.jsonb_typeof(value) == "array", value), else_=empty)
        return func.jsonb_array_elements(array).table_valued(column("value", JSONB), with_ordinality="position").render_derived()

    objects = elements("objects")
    obj = objects.c.value
    identity = func.coalesce(obj["id"].as_string(), obj["object_id"].as_string())
    party = obj["party_no"].as_string()
    exam = obj["examination_no"].as_string()
    year = obj["examination_year"].as_string()
    object_summary = select(func.jsonb_build_object(
        "object_count", func.count(distinct(func.concat(func.coalesce(obj["source_kind"].as_string(), "chs"), ":", identity))).filter(identity.is_not(None)),
        "party_numbers", func.coalesce(func.jsonb_agg(distinct(party)).filter(and_(party.is_not(None), party != "")), empty),
        "examination_names", func.coalesce(func.jsonb_agg(distinct(func.concat(exam, "-", year))).filter(and_(exam.is_not(None), exam != "", year.is_not(None))), empty),
    )).select_from(objects).correlate(LabProtocol).scalar_subquery()

    stages = elements("stages")
    stage_summary = select(func.coalesce(
        func.jsonb_agg(aggregate_order_by(stages.c.value["stage_type"].as_string(), stages.c.position)).filter(stages.c.value["enabled"].as_boolean().is_(True)), empty,
    )).select_from(stages).correlate(LabProtocol).scalar_subquery()
    return select(
        LabProtocol.id, LabProtocol.kind, LabProtocol.series_key, LabProtocol.protocol_no,
        LabProtocol.protocol_date, LabProtocol.name, LabProtocol.status, LabProtocol.revision_no,
        LabProtocol.created_by_user_id, LabProtocol.updated_at,
        object_summary.label("object_summary"), stage_summary.label("stage_types"),
    )
