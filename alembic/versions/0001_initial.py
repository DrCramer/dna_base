"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

role_enum = postgresql.ENUM("admin", "user", "viewer", name="userrole", create_type=False)


def json_type():
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'userrole') THEN
                    CREATE TYPE userrole AS ENUM ('admin', 'user', 'viewer');
                END IF;
            END$$;
            """
        )
        json_col = json_type()
        user_role = role_enum
    else:
        json_col = sa.JSON()
        user_role = sa.Enum("admin", "user", "viewer", name="userrole")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(80), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("full_name", sa.String(255), nullable=False, unique=True),
        sa.Column("short_name", sa.String(80)),
        sa.Column("is_active", sa.Boolean(), nullable=False),
    )

    op.create_table(
        "registry_import_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("stored_path", sa.String(500)),
        sa.Column("imported_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("rows_total", sa.Integer(), nullable=False),
        sa.Column("rows_imported", sa.Integer(), nullable=False),
        sa.Column("rows_skipped", sa.Integer(), nullable=False),
        sa.Column("import_log_json", json_col, nullable=False),
    )
    op.create_index("ix_registry_import_batches_file_sha256", "registry_import_batches", ["file_sha256"])

    op.create_table(
        "objects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_import_batch_id", sa.Integer(), sa.ForeignKey("registry_import_batches.id", ondelete="SET NULL")),
        sa.Column("source_sheet_name", sa.String(120)),
        sa.Column("source_row_number", sa.Integer()),
        sa.Column("registry_row_no", sa.String(80)),
        sa.Column("intake_date", sa.Date()),
        sa.Column("decision_date", sa.Date()),
        sa.Column("investigator", sa.String(255)),
        sa.Column("incoming_no", sa.String(120)),
        sa.Column("decree_no", sa.String(120)),
        sa.Column("decree_no_base", sa.String(80)),
        sa.Column("object_description", sa.Text()),
        sa.Column("external_military_no", sa.String(255)),
        sa.Column("extraction_note", sa.String(255)),
        sa.Column("box_no", sa.String(80)),
        sa.Column("packages_count", sa.Integer()),
        sa.Column("rcsme_reg_no", sa.String(120)),
        sa.Column("rcsme_reg_no_base", sa.String(80)),
        sa.Column("object_type", sa.String(255)),
        sa.Column("extracted_before", sa.String(255)),
        sa.Column("not_extracted_before", sa.String(255)),
        sa.Column("registry_filled_by", sa.String(255)),
        sa.Column("status", sa.String(80), nullable=False),
        sa.Column("raw_registry_json", json_col, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("rcsme_reg_no", name="uq_objects_rcsme_reg_no"),
        sa.UniqueConstraint("decree_no", name="uq_objects_decree_no"),
    )
    for col in [
        "source_import_batch_id",
        "investigator",
        "decree_no",
        "decree_no_base",
        "external_military_no",
        "box_no",
        "rcsme_reg_no",
        "rcsme_reg_no_base",
        "object_type",
        "status",
    ]:
        op.create_index(f"ix_objects_{col}", "objects", [col])
    op.create_index("ix_objects_search_numbers", "objects", ["rcsme_reg_no", "decree_no", "external_military_no"])
    if bind.dialect.name == "postgresql":
        op.create_index("ix_objects_description_trgm", "objects", ["object_description"], postgresql_using="gin", postgresql_ops={"object_description": "gin_trgm_ops"})
        op.create_index("ix_objects_rcsme_trgm", "objects", ["rcsme_reg_no"], postgresql_using="gin", postgresql_ops={"rcsme_reg_no": "gin_trgm_ops"})
        op.create_index("ix_objects_decree_trgm", "objects", ["decree_no"], postgresql_using="gin", postgresql_ops={"decree_no": "gin_trgm_ops"})

    op.create_table(
        "object_prep_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("object_id", sa.Integer(), sa.ForeignKey("objects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_type", sa.String(80), nullable=False),
        sa.Column("performer", sa.String(255)),
        sa.Column("assistant", sa.String(255)),
        sa.Column("event_date", sa.Date()),
        sa.Column("comment", sa.Text()),
        sa.Column("raw_json", json_col, nullable=False),
    )
    op.create_index("ix_object_prep_events_object_id", "object_prep_events", ["object_id"])
    op.create_index("ix_object_prep_events_stage_type", "object_prep_events", ["stage_type"])
    op.create_index("ix_object_prep_events_event_date", "object_prep_events", ["event_date"])

    op.create_table(
        "dna_extractions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("object_id", sa.Integer(), sa.ForeignKey("objects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extraction_no", sa.Integer(), nullable=False),
        sa.Column("extraction_date", sa.Date()),
        sa.Column("performer", sa.String(255)),
        sa.Column("extraction_method", sa.String(255)),
        sa.Column("quant_method", sa.String(255)),
        sa.Column("quant_date", sa.Date()),
        sa.Column("quant_performer", sa.String(255)),
        sa.Column("pipetting_method", sa.String(255)),
        sa.Column("comment", sa.Text()),
        sa.Column("raw_json", json_col, nullable=False),
    )
    for col in ["object_id", "extraction_date", "performer", "extraction_method", "quant_method", "quant_date"]:
        op.create_index(f"ix_dna_extractions_{col}", "dna_extractions", [col])

    op.create_table(
        "pcr_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("object_id", sa.Integer(), sa.ForeignKey("objects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pcr_date", sa.Date()),
        sa.Column("locus_panel", sa.String(255)),
        sa.Column("pipetting_method", sa.String(255)),
        sa.Column("normalization_performer", sa.String(255)),
        sa.Column("pcr_performer", sa.String(255)),
        sa.Column("comment", sa.Text()),
        sa.Column("raw_json", json_col, nullable=False),
    )
    for col in ["object_id", "pcr_date", "locus_panel", "pcr_performer"]:
        op.create_index(f"ix_pcr_events_{col}", "pcr_events", [col])

    op.create_table(
        "electrophoresis_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("object_id", sa.Integer(), sa.ForeignKey("objects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("electrophoresis_date", sa.Date()),
        sa.Column("sequencer", sa.String(255)),
        sa.Column("pipetting_method", sa.String(255)),
        sa.Column("performer_1", sa.String(255)),
        sa.Column("performer_2", sa.String(255)),
        sa.Column("genotype", sa.String(255)),
        sa.Column("comment", sa.Text()),
        sa.Column("raw_json", json_col, nullable=False),
    )
    for col in ["object_id", "electrophoresis_date", "sequencer"]:
        op.create_index(f"ix_electrophoresis_events_{col}", "electrophoresis_events", [col])

    op.create_table(
        "electrophoresis_analysis_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("object_id", sa.Integer(), sa.ForeignKey("objects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("analysis_date", sa.Date()),
        sa.Column("performer", sa.String(255)),
        sa.Column("result_status", sa.String(120)),
        sa.Column("comment", sa.Text()),
        sa.Column("raw_json", json_col, nullable=False),
    )
    for col in ["object_id", "analysis_date", "performer", "result_status"]:
        op.create_index(f"ix_electrophoresis_analysis_events_{col}", "electrophoresis_analysis_events", [col])

    op.create_table(
        "rt_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("imported_file_id", sa.Integer()),
        sa.Column("run_name", sa.String(255)),
        sa.Column("run_date", sa.DateTime(timezone=True)),
        sa.Column("instrument", sa.String(255)),
        sa.Column("kit", sa.String(255)),
        sa.Column("plate_name", sa.String(255)),
        sa.Column("operator", sa.String(255)),
        sa.Column("quant_method", sa.String(255)),
        sa.Column("comment", sa.Text()),
        sa.Column("raw_json", json_col, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_rt_runs_run_date", "rt_runs", ["run_date"])

    op.create_table(
        "rt_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rt_run_id", sa.Integer(), sa.ForeignKey("rt_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("object_id", sa.Integer(), sa.ForeignKey("objects.id", ondelete="SET NULL")),
        sa.Column("sample_name_raw", sa.String(255)),
        sa.Column("normalized_sample_name", sa.String(255)),
        sa.Column("sample_base", sa.String(80)),
        sa.Column("well", sa.String(40)),
        sa.Column("target", sa.String(255)),
        sa.Column("ct", sa.Float()),
        sa.Column("cq", sa.Float()),
        sa.Column("quantity_ng_ul", sa.Float()),
        sa.Column("mean_quantity_ng_ul", sa.Float()),
        sa.Column("degradation_index", sa.Float()),
        sa.Column("ipc_ct", sa.Float()),
        sa.Column("y_quantity", sa.Float()),
        sa.Column("replicate_no", sa.Integer()),
        sa.Column("result_flag", sa.String(255)),
        sa.Column("raw_json", json_col, nullable=False),
    )
    for col in ["rt_run_id", "object_id", "sample_name_raw", "normalized_sample_name", "sample_base"]:
        op.create_index(f"ix_rt_results_{col}", "rt_results", [col])

    op.create_table(
        "electrophoresis_result_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("object_id", sa.Integer(), sa.ForeignKey("objects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.Integer()),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_type", sa.String(80)),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("raw_json", json_col, nullable=False),
    )
    op.create_index("ix_electrophoresis_result_files_object_id", "electrophoresis_result_files", ["object_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("entity_type", sa.String(120), nullable=False),
        sa.Column("entity_id", sa.String(120), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("before_json", json_col),
        sa.Column("after_json", json_col),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    for col in ["user_id", "entity_type", "entity_id", "action", "created_at"]:
        op.create_index(f"ix_audit_log_{col}", "audit_log", [col])


def downgrade() -> None:
    for table in [
        "audit_log",
        "electrophoresis_result_files",
        "rt_results",
        "rt_runs",
        "electrophoresis_analysis_events",
        "electrophoresis_events",
        "pcr_events",
        "dna_extractions",
        "object_prep_events",
        "objects",
        "registry_import_batches",
        "employees",
        "users",
    ]:
        op.drop_table(table)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        role_enum.drop(bind, checkfirst=True)
