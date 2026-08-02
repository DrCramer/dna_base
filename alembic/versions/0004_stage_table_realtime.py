"""stage table realtime fields and sample prep canonicalization

Revision ID: 0004_stage_table_realtime
Revises: 0003_canonical_model
Create Date: 2026-06-27
"""
from __future__ import annotations

from datetime import date
import json
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_stage_table_realtime"
down_revision: Union[str, None] = "0003_canonical_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _merge_unique(*values: Any) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in _as_list(value):
            if item not in seen:
                seen.add(item)
                merged.append(item)
    return merged


def _latest(*values: date | None) -> date | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _comment(*values: str | None) -> str | None:
    merged: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = (value or "").strip()
        if text and text not in seen:
            seen.add(text)
            merged.append(text)
    return "; ".join(merged) if merged else None


def _canonicalize_sample_prep() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    rows = bind.execute(
        sa.text(
            """
            SELECT
                e.id,
                e.object_id,
                e.attempt_no,
                e.event_date,
                e.comment,
                e.raw_json,
                d.registry_filled_by,
                d.photo_performers,
                d.photo_assistants,
                d.washing_performers,
                d.washing_assistants,
                d.washing_date,
                d.bone_tissue_performers,
                d.bone_tissue_date
            FROM stage_events e
            LEFT JOIN sample_prep_details d ON d.stage_event_id = e.id
            WHERE e.stage_type = 'sample_prep'
              AND e.source = 'registry_excel'
              AND e.is_cancelled = false
              AND e.raw_json ? 'source_row_number'
            ORDER BY e.object_id, e.id
            """
        )
    ).mappings().all()
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        raw = row["raw_json"] or {}
        key = (
            row["object_id"],
            raw.get("source_import_batch_id"),
            raw.get("source_file_sha256"),
            raw.get("source_row_number"),
            raw.get("source_sheet_name"),
        )
        groups.setdefault(key, []).append(dict(row))

    for key, items in groups.items():
        if len(items) < 2:
            continue
        if any((item.get("raw_json") or {}).get("canonicalized_sample_prep") for item in items):
            continue
        raw_values = [item.get("raw_json") or {} for item in items]
        source_blocks = sorted({raw.get("block") for raw in raw_values if raw.get("block")})
        raw_json = {
            **raw_values[0],
            "source": "registry_excel",
            "block": "sample_prep",
            "source_blocks": source_blocks,
            "canonical_stage_type": "sample_prep",
            "canonicalized_sample_prep": True,
            "canonicalized_from_stage_event_ids": [item["id"] for item in items],
        }
        event_date = _latest(
            *(item.get("event_date") for item in items),
            *(item.get("washing_date") for item in items),
            *(item.get("bone_tissue_date") for item in items),
        )
        new_id = bind.execute(
            sa.text(
                """
                INSERT INTO stage_events (
                    object_id, stage_type, attempt_no, event_date, source, comment, raw_json,
                    created_at, updated_at, is_cancelled
                )
                VALUES (
                    :object_id, 'sample_prep', :attempt_no, :event_date, 'registry_excel',
                    :comment, CAST(:raw_json AS JSONB), now(), now(), false
                )
                RETURNING id
                """
            ),
            {
                "object_id": key[0],
                "attempt_no": min(item["attempt_no"] or 1 for item in items),
                "event_date": event_date,
                "comment": _comment(*(item.get("comment") for item in items)),
                "raw_json": json.dumps(raw_json, ensure_ascii=False),
            },
        ).scalar_one()
        bind.execute(
            sa.text(
                """
                INSERT INTO sample_prep_details (
                    stage_event_id,
                    registry_filled_by,
                    photo_performers,
                    photo_assistants,
                    washing_performers,
                    washing_assistants,
                    washing_date,
                    bone_tissue_performers,
                    bone_tissue_date
                )
                VALUES (
                    :stage_event_id,
                    :registry_filled_by,
                    CAST(:photo_performers AS JSONB),
                    CAST(:photo_assistants AS JSONB),
                    CAST(:washing_performers AS JSONB),
                    CAST(:washing_assistants AS JSONB),
                    :washing_date,
                    CAST(:bone_tissue_performers AS JSONB),
                    :bone_tissue_date
                )
                """
            ),
            {
                "stage_event_id": new_id,
                "registry_filled_by": next((item.get("registry_filled_by") for item in items if item.get("registry_filled_by")), None),
                "photo_performers": json.dumps(_merge_unique(*(item.get("photo_performers") for item in items)), ensure_ascii=False),
                "photo_assistants": json.dumps(_merge_unique(*(item.get("photo_assistants") for item in items)), ensure_ascii=False),
                "washing_performers": json.dumps(_merge_unique(*(item.get("washing_performers") for item in items)), ensure_ascii=False),
                "washing_assistants": json.dumps(_merge_unique(*(item.get("washing_assistants") for item in items)), ensure_ascii=False),
                "washing_date": _latest(*(item.get("washing_date") for item in items)),
                "bone_tissue_performers": json.dumps(_merge_unique(*(item.get("bone_tissue_performers") for item in items)), ensure_ascii=False),
                "bone_tissue_date": _latest(*(item.get("bone_tissue_date") for item in items)),
            },
        )
        marker = json.dumps({"canonicalized_into_stage_event_id": new_id}, ensure_ascii=False)
        for item in items:
            bind.execute(
                sa.text(
                    """
                    UPDATE stage_events
                    SET is_cancelled = true,
                        raw_json = coalesce(raw_json, '{}'::jsonb) || CAST(:marker AS JSONB),
                        updated_at = now()
                    WHERE id = :id
                    """
                ),
                {"id": item["id"], "marker": marker},
            )


def upgrade() -> None:
    op.add_column("realtime_details", sa.Column("concentration", sa.Float(), nullable=True))
    op.add_column("realtime_details", sa.Column("ct_cq", sa.Float(), nullable=True))
    op.add_column("realtime_details", sa.Column("di", sa.Float(), nullable=True))
    op.add_column("realtime_details", sa.Column("ipc", sa.Float(), nullable=True))
    _canonicalize_sample_prep()


def downgrade() -> None:
    op.drop_column("realtime_details", "ipc")
    op.drop_column("realtime_details", "di")
    op.drop_column("realtime_details", "ct_cq")
    op.drop_column("realtime_details", "concentration")
