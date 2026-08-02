"""canonical parties, work sessions and repeatable stage events

Revision ID: 0003_canonical_model
Revises: 0002_party_numbers
Create Date: 2026-06-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0003_canonical_model"
down_revision: Union[str, None] = "0002_party_numbers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def json_type():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def _create_index(table: str, column: str, *, unique: bool = False) -> None:
    op.create_index(f"ix_{table}_{column}", table, [column], unique=unique)


def _backfill_parties() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        INSERT INTO parties (
            party_no, title, status, object_count, raw_control_json, created_at, updated_at
        )
        SELECT party_no, party_no, 'active', 0, '{}'::jsonb, now(), now()
        FROM (
            SELECT party_no FROM objects WHERE party_no IS NOT NULL AND btrim(party_no) <> ''
            UNION
            SELECT party_no FROM registry_import_batches WHERE party_no IS NOT NULL AND btrim(party_no) <> ''
        ) source_parties
        ON CONFLICT (party_no) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE objects objects_table
        SET party_id = parties.id
        FROM parties
        WHERE objects_table.party_id IS NULL
          AND objects_table.party_no = parties.party_no
        """
    )
    op.execute(
        """
        UPDATE parties
        SET object_count = object_counts.count_value
        FROM (
            SELECT party_id, count(*) AS count_value
            FROM objects
            WHERE party_id IS NOT NULL
            GROUP BY party_id
        ) object_counts
        WHERE parties.id = object_counts.party_id
        """
    )


def _migrate_legacy_stage_events() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        INSERT INTO stage_events (
            object_id, stage_type, attempt_no, event_date, source, comment, raw_json, created_at, updated_at
        )
        SELECT
            legacy.object_id,
            CASE WHEN legacy.stage_type = 'mill_grinding' THEN 'milling' ELSE 'sample_prep' END,
            row_number() OVER (
                PARTITION BY legacy.object_id, legacy.stage_type
                ORDER BY legacy.event_date NULLS LAST, legacy.id
            )::integer,
            legacy.event_date,
            coalesce(nullif(legacy.raw_json->>'source', ''), 'legacy'),
            legacy.comment,
            jsonb_build_object(
                'source', 'legacy_migration',
                'legacy_table', 'object_prep_events',
                'legacy_id', legacy.id,
                'legacy_stage_type', legacy.stage_type,
                'block', legacy.raw_json->>'block',
                'raw', coalesce(legacy.raw_json, '{}'::jsonb)
            ),
            now(),
            now()
        FROM object_prep_events legacy
        WHERE NOT EXISTS (
            SELECT 1
            FROM stage_events existing
            WHERE existing.raw_json->>'legacy_table' = 'object_prep_events'
              AND (existing.raw_json->>'legacy_id')::integer = legacy.id
        )
        """
    )
    op.execute(
        """
        INSERT INTO stage_events (
            object_id, stage_type, attempt_no, event_date, source, comment, raw_json, created_at, updated_at
        )
        SELECT
            legacy.object_id,
            'dna_extraction',
            coalesce(legacy.extraction_no, 1),
            legacy.extraction_date,
            coalesce(nullif(legacy.raw_json->>'source', ''), 'legacy'),
            legacy.comment,
            jsonb_build_object(
                'source', 'legacy_migration',
                'legacy_table', 'dna_extractions',
                'legacy_id', legacy.id,
                'block', legacy.raw_json->>'block',
                'raw', coalesce(legacy.raw_json, '{}'::jsonb)
            ),
            now(),
            now()
        FROM dna_extractions legacy
        WHERE NOT EXISTS (
            SELECT 1
            FROM stage_events existing
            WHERE existing.raw_json->>'legacy_table' = 'dna_extractions'
              AND (existing.raw_json->>'legacy_id')::integer = legacy.id
              AND existing.stage_type = 'dna_extraction'
        )
        """
    )
    op.execute(
        """
        INSERT INTO stage_events (
            object_id, stage_type, attempt_no, event_date, source, comment, raw_json, created_at, updated_at
        )
        SELECT
            legacy.object_id,
            'realtime',
            coalesce(legacy.extraction_no, 1),
            legacy.quant_date,
            coalesce(nullif(legacy.raw_json->>'source', ''), 'legacy'),
            legacy.comment,
            jsonb_build_object(
                'source', 'legacy_migration',
                'legacy_table', 'dna_extractions',
                'legacy_id', legacy.id,
                'legacy_stage_type', 'realtime',
                'block', legacy.raw_json->>'block',
                'raw', coalesce(legacy.raw_json, '{}'::jsonb)
            ),
            now(),
            now()
        FROM dna_extractions legacy
        WHERE (
            legacy.quant_method IS NOT NULL OR legacy.quant_date IS NOT NULL
            OR legacy.quant_performer IS NOT NULL OR legacy.pipetting_method IS NOT NULL
        )
          AND NOT EXISTS (
            SELECT 1
            FROM stage_events existing
            WHERE existing.raw_json->>'legacy_table' = 'dna_extractions'
              AND (existing.raw_json->>'legacy_id')::integer = legacy.id
              AND existing.stage_type = 'realtime'
        )
        """
    )
    op.execute(
        """
        INSERT INTO stage_events (
            object_id, stage_type, attempt_no, event_date, source, comment, raw_json, created_at, updated_at
        )
        SELECT
            legacy.object_id,
            'pcr',
            row_number() OVER (
                PARTITION BY legacy.object_id
                ORDER BY legacy.pcr_date NULLS LAST, legacy.id
            )::integer,
            legacy.pcr_date,
            coalesce(nullif(legacy.raw_json->>'source', ''), 'legacy'),
            legacy.comment,
            jsonb_build_object(
                'source', 'legacy_migration',
                'legacy_table', 'pcr_events',
                'legacy_id', legacy.id,
                'block', legacy.raw_json->>'block',
                'raw', coalesce(legacy.raw_json, '{}'::jsonb)
            ),
            now(),
            now()
        FROM pcr_events legacy
        WHERE NOT EXISTS (
            SELECT 1
            FROM stage_events existing
            WHERE existing.raw_json->>'legacy_table' = 'pcr_events'
              AND (existing.raw_json->>'legacy_id')::integer = legacy.id
        )
        """
    )
    op.execute(
        """
        INSERT INTO stage_events (
            object_id, stage_type, attempt_no, event_date, source, comment, raw_json, created_at, updated_at
        )
        SELECT
            legacy.object_id,
            'electrophoresis',
            row_number() OVER (
                PARTITION BY legacy.object_id
                ORDER BY legacy.electrophoresis_date NULLS LAST, legacy.id
            )::integer,
            legacy.electrophoresis_date,
            coalesce(nullif(legacy.raw_json->>'source', ''), 'legacy'),
            legacy.comment,
            jsonb_build_object(
                'source', 'legacy_migration',
                'legacy_table', 'electrophoresis_events',
                'legacy_id', legacy.id,
                'block', legacy.raw_json->>'block',
                'raw', coalesce(legacy.raw_json, '{}'::jsonb)
            ),
            now(),
            now()
        FROM electrophoresis_events legacy
        WHERE NOT EXISTS (
            SELECT 1
            FROM stage_events existing
            WHERE existing.raw_json->>'legacy_table' = 'electrophoresis_events'
              AND (existing.raw_json->>'legacy_id')::integer = legacy.id
        )
        """
    )
    op.execute(
        """
        INSERT INTO stage_events (
            object_id, stage_type, attempt_no, event_date, source, comment, raw_json, created_at, updated_at
        )
        SELECT
            legacy.object_id,
            'analysis',
            coalesce(legacy.attempt_no, 1),
            legacy.analysis_date,
            coalesce(nullif(legacy.raw_json->>'source', ''), 'legacy'),
            legacy.comment,
            jsonb_build_object(
                'source', 'legacy_migration',
                'legacy_table', 'electrophoresis_analysis_events',
                'legacy_id', legacy.id,
                'block', legacy.raw_json->>'block',
                'raw', coalesce(legacy.raw_json, '{}'::jsonb)
            ),
            now(),
            now()
        FROM electrophoresis_analysis_events legacy
        WHERE NOT EXISTS (
            SELECT 1
            FROM stage_events existing
            WHERE existing.raw_json->>'legacy_table' = 'electrophoresis_analysis_events'
              AND (existing.raw_json->>'legacy_id')::integer = legacy.id
        )
        """
    )


def upgrade() -> None:
    json_col = json_type()

    op.add_column("employees", sa.Column("initials", sa.String(80), nullable=True))
    op.add_column("employees", sa.Column("role", sa.String(120), nullable=True))
    op.add_column(
        "employees",
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    _create_index("employees", "initials")
    _create_index("employees", "role")

    op.create_table(
        "parties",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("party_no", sa.String(80), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("status", sa.String(80), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("object_count", sa.Integer(), nullable=False),
        sa.Column("control_actual_decrees", sa.Text(), nullable=True),
        sa.Column("control_decree_without_object", sa.Text(), nullable=True),
        sa.Column("control_object_without_decree", sa.Text(), nullable=True),
        sa.Column("control_unidentified_rostov_no", sa.Text(), nullable=True),
        sa.Column("control_need_recall", sa.Text(), nullable=True),
        sa.Column("control_recalled", sa.Text(), nullable=True),
        sa.Column("raw_control_json", json_col, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    _create_index("parties", "party_no", unique=True)
    _create_index("parties", "status")
    _create_index("parties", "created_by_user_id")

    op.add_column("objects", sa.Column("party_id", sa.Integer(), nullable=True))
    op.add_column(
        "objects",
        sa.Column("rcsme_reg_no_is_manual", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_foreign_key("fk_objects_party_id_parties", "objects", "parties", ["party_id"], ["id"], ondelete="SET NULL")
    _create_index("objects", "party_id")
    _create_index("objects", "rcsme_reg_no_is_manual")

    op.create_table(
        "work_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("party_id", sa.Integer(), sa.ForeignKey("parties.id", ondelete="SET NULL"), nullable=True),
        sa.Column("stage_type", sa.String(80), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("work_date", sa.Date(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("status", sa.String(80), nullable=False),
        sa.Column("raw_json", json_col, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    for column in ["party_id", "stage_type", "work_date", "created_by_user_id", "source", "status"]:
        _create_index("work_sessions", column)

    op.create_table(
        "work_session_objects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("work_session_id", sa.Integer(), sa.ForeignKey("work_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("object_id", sa.Integer(), sa.ForeignKey("objects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("object_order", sa.Integer(), nullable=True),
        sa.Column("per_object_comment", sa.Text(), nullable=True),
        sa.Column("is_excluded", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("work_session_id", "object_id", name="uq_work_session_objects_once"),
    )
    _create_index("work_session_objects", "work_session_id")
    _create_index("work_session_objects", "object_id")

    op.create_table(
        "stage_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("object_id", sa.Integer(), sa.ForeignKey("objects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_session_id", sa.Integer(), sa.ForeignKey("work_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("stage_type", sa.String(80), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("raw_json", json_col, nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_cancelled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    for column in [
        "object_id",
        "work_session_id",
        "stage_type",
        "attempt_no",
        "event_date",
        "source",
        "created_by_user_id",
        "is_cancelled",
    ]:
        _create_index("stage_events", column)
    op.create_index(
        "ix_stage_events_object_stage_attempt",
        "stage_events",
        ["object_id", "stage_type", "attempt_no"],
    )

    op.create_table(
        "stage_event_performers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stage_event_id", sa.Integer(), sa.ForeignKey("stage_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("role", sa.String(120), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("raw_name", sa.String(255), nullable=True),
    )
    for column in ["stage_event_id", "employee_id", "role", "raw_name"]:
        _create_index("stage_event_performers", column)

    op.create_table(
        "sample_prep_details",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stage_event_id", sa.Integer(), sa.ForeignKey("stage_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("registry_filled_by", sa.String(255), nullable=True),
        sa.Column("photo_performers", json_col, nullable=False),
        sa.Column("photo_assistants", json_col, nullable=False),
        sa.Column("washing_performers", json_col, nullable=False),
        sa.Column("washing_assistants", json_col, nullable=False),
        sa.Column("washing_date", sa.Date(), nullable=True),
        sa.Column("bone_tissue_performers", json_col, nullable=False),
        sa.Column("bone_tissue_date", sa.Date(), nullable=True),
        sa.UniqueConstraint("stage_event_id", name="uq_sample_prep_details_stage_event_id"),
    )
    _create_index("sample_prep_details", "stage_event_id")
    _create_index("sample_prep_details", "washing_date")
    _create_index("sample_prep_details", "bone_tissue_date")

    op.create_table(
        "milling_details",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stage_event_id", sa.Integer(), sa.ForeignKey("stage_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("milling_performers", json_col, nullable=False),
        sa.Column("cups", sa.String(255), nullable=True),
        sa.Column("milling_date", sa.Date(), nullable=True),
        sa.UniqueConstraint("stage_event_id", name="uq_milling_details_stage_event_id"),
    )
    _create_index("milling_details", "stage_event_id")
    _create_index("milling_details", "milling_date")

    op.create_table(
        "dna_extraction_details",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stage_event_id", sa.Integer(), sa.ForeignKey("stage_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extraction_date", sa.Date(), nullable=True),
        sa.Column("extraction_method", sa.String(255), nullable=True),
        sa.UniqueConstraint("stage_event_id", name="uq_dna_extraction_details_stage_event_id"),
    )
    _create_index("dna_extraction_details", "stage_event_id")
    _create_index("dna_extraction_details", "extraction_date")
    _create_index("dna_extraction_details", "extraction_method")

    op.create_table(
        "realtime_details",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stage_event_id", sa.Integer(), sa.ForeignKey("stage_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quant_method", sa.String(255), nullable=True),
        sa.Column("quant_date", sa.Date(), nullable=True),
        sa.Column("quant_performer", sa.String(255), nullable=True),
        sa.Column("pipetting_method", sa.String(255), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.UniqueConstraint("stage_event_id", name="uq_realtime_details_stage_event_id"),
    )
    for column in ["stage_event_id", "quant_method", "quant_date"]:
        _create_index("realtime_details", column)

    op.create_table(
        "pcr_details",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stage_event_id", sa.Integer(), sa.ForeignKey("stage_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pcr_date", sa.Date(), nullable=True),
        sa.Column("locus_panel", sa.String(255), nullable=True),
        sa.Column("pipetting_method", sa.String(255), nullable=True),
        sa.Column("normalization_performers", json_col, nullable=False),
        sa.Column("pcr_performers", json_col, nullable=False),
        sa.UniqueConstraint("stage_event_id", name="uq_pcr_details_stage_event_id"),
    )
    for column in ["stage_event_id", "pcr_date", "locus_panel"]:
        _create_index("pcr_details", column)

    op.create_table(
        "electrophoresis_details",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stage_event_id", sa.Integer(), sa.ForeignKey("stage_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("electrophoresis_date", sa.Date(), nullable=True),
        sa.Column("sequencer", sa.String(255), nullable=True),
        sa.Column("pipetting_method", sa.String(255), nullable=True),
        sa.Column("performers", json_col, nullable=False),
        sa.UniqueConstraint("stage_event_id", name="uq_electrophoresis_details_stage_event_id"),
    )
    for column in ["stage_event_id", "electrophoresis_date", "sequencer"]:
        _create_index("electrophoresis_details", column)

    op.create_table(
        "analysis_details",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stage_event_id", sa.Integer(), sa.ForeignKey("stage_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("genotype", sa.String(255), nullable=True),
        sa.Column("analysis_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(120), nullable=True),
        sa.UniqueConstraint("stage_event_id", name="uq_analysis_details_stage_event_id"),
    )
    for column in ["stage_event_id", "genotype", "analysis_date", "status"]:
        _create_index("analysis_details", column)

    _backfill_parties()
    _migrate_legacy_stage_events()


def downgrade() -> None:
    op.drop_table("analysis_details")
    op.drop_table("electrophoresis_details")
    op.drop_table("pcr_details")
    op.drop_table("realtime_details")
    op.drop_table("dna_extraction_details")
    op.drop_table("milling_details")
    op.drop_table("sample_prep_details")
    op.drop_table("stage_event_performers")
    op.drop_index("ix_stage_events_object_stage_attempt", table_name="stage_events")
    op.drop_table("stage_events")
    op.drop_table("work_session_objects")
    op.drop_table("work_sessions")
    op.drop_index("ix_objects_rcsme_reg_no_is_manual", table_name="objects")
    op.drop_index("ix_objects_party_id", table_name="objects")
    op.drop_constraint("fk_objects_party_id_parties", "objects", type_="foreignkey")
    op.drop_column("objects", "rcsme_reg_no_is_manual")
    op.drop_column("objects", "party_id")
    op.drop_table("parties")
    op.drop_index("ix_employees_role", table_name="employees")
    op.drop_index("ix_employees_initials", table_name="employees")
    op.drop_column("employees", "is_verified")
    op.drop_column("employees", "role")
    op.drop_column("employees", "initials")
