"""Add saved laboratory protocols and profiles.

Revision ID: 0013_lab_protocols
Revises: 0012_object_material_flags
Create Date: 2026-09-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0013_lab_protocols"
down_revision = "0012_object_material_flags"
branch_labels = None
depends_on = None

json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "protocol_stage_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stage_type", sa.String(80), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("reference_item_id", sa.Integer(), sa.ForeignKey("reference_items.id", ondelete="SET NULL")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("plate_rules_json", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("reagent_config_json", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("instrument_config_json", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("stage_type", "name", name="uq_protocol_stage_profiles_stage_name"),
    )
    op.create_index("ix_protocol_stage_profiles_stage_type", "protocol_stage_profiles", ["stage_type"])
    op.create_index("ix_protocol_stage_profiles_name", "protocol_stage_profiles", ["name"])
    op.create_index("ix_protocol_stage_profiles_reference_item_id", "protocol_stage_profiles", ["reference_item_id"])
    op.create_index("ix_protocol_stage_profiles_active", "protocol_stage_profiles", ["active"])

    op.create_table(
        "lab_protocols",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("series_key", sa.String(36), nullable=False),
        sa.Column("protocol_no", sa.Integer(), nullable=False),
        sa.Column("protocol_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="draft"),
        sa.Column("revision_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("comment", sa.Text()),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("finalized_at", sa.DateTime(timezone=True)),
        sa.Column("snapshot_json", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("series_key", "revision_no", name="uq_lab_protocols_series_revision"),
        sa.UniqueConstraint("protocol_date", "protocol_no", "revision_no", name="uq_lab_protocols_date_no_revision"),
    )
    for column in ("series_key", "protocol_no", "protocol_date", "name", "status", "is_current", "created_by_user_id"):
        op.create_index(f"ix_lab_protocols_{column}", "lab_protocols", [column])
    op.create_index("ix_lab_protocols_current_status", "lab_protocols", ["is_current", "status"])

    op.create_table(
        "lab_protocol_stages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("protocol_id", sa.Integer(), sa.ForeignKey("lab_protocols.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_type", sa.String(80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("work_date", sa.Date()),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("protocol_stage_profiles.id", ondelete="SET NULL")),
        sa.Column("kit_name_snapshot", sa.String(255)),
        sa.Column("sequencer_name_snapshot", sa.String(255)),
        sa.Column("comment", sa.Text()),
        sa.Column("settings_json", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("protocol_id", "stage_type", name="uq_lab_protocol_stages_once"),
    )
    for column in ("protocol_id", "stage_type", "work_date", "profile_id", "kit_name_snapshot", "sequencer_name_snapshot"):
        op.create_index(f"ix_lab_protocol_stages_{column}", "lab_protocol_stages", [column])

    op.create_table(
        "lab_protocol_stage_performers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("protocol_stage_id", sa.Integer(), sa.ForeignKey("lab_protocol_stages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="SET NULL")),
        sa.Column("display_name_snapshot", sa.String(255), nullable=False),
        sa.Column("role", sa.String(120)),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
    )
    for column in ("protocol_stage_id", "employee_id", "display_name_snapshot"):
        op.create_index(f"ix_lab_protocol_stage_performers_{column}", "lab_protocol_stage_performers", [column])

    op.create_table(
        "lab_protocol_objects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("protocol_id", sa.Integer(), sa.ForeignKey("lab_protocols.id", ondelete="CASCADE"), nullable=False),
        sa.Column("object_id", sa.Integer(), sa.ForeignKey("objects.id", ondelete="SET NULL")),
        sa.Column("party_id", sa.Integer(), sa.ForeignKey("parties.id", ondelete="SET NULL")),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("rcsme_no_snapshot", sa.String(120)),
        sa.Column("decision_no_snapshot", sa.String(120)),
        sa.Column("military_no_snapshot", sa.String(255)),
        sa.Column("object_type_snapshot", sa.String(255)),
        sa.Column("party_no_snapshot", sa.String(80)),
        sa.Column("box_no_snapshot", sa.String(80)),
        sa.Column("snapshot_json", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("protocol_id", "order_index", name="uq_lab_protocol_objects_order"),
    )
    for column in ("protocol_id", "object_id", "party_id", "rcsme_no_snapshot", "decision_no_snapshot", "military_no_snapshot", "party_no_snapshot"):
        op.create_index(f"ix_lab_protocol_objects_{column}", "lab_protocol_objects", [column])

    op.create_table(
        "lab_protocol_wells",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("protocol_id", sa.Integer(), sa.ForeignKey("lab_protocols.id", ondelete="CASCADE"), nullable=False),
        sa.Column("protocol_stage_id", sa.Integer(), sa.ForeignKey("lab_protocol_stages.id", ondelete="CASCADE")),
        sa.Column("layout_key", sa.String(80), nullable=False, server_default="source"),
        sa.Column("plate_index", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("well", sa.String(8), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("object_id", sa.Integer(), sa.ForeignKey("objects.id", ondelete="SET NULL")),
        sa.Column("label", sa.String(255)),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("protocol_id", "layout_key", "plate_index", "well", name="uq_lab_protocol_wells_position"),
    )
    for column in ("protocol_id", "protocol_stage_id", "layout_key", "kind", "object_id"):
        op.create_index(f"ix_lab_protocol_wells_{column}", "lab_protocol_wells", [column])

    op.create_table(
        "protocol_exports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("protocol_id", sa.Integer(), sa.ForeignKey("lab_protocols.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_type", sa.String(80)),
        sa.Column("exporter_key", sa.String(120), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("storage_path", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("metadata_json", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    for column in ("protocol_id", "stage_type", "exporter_key", "created_by_user_id"):
        op.create_index(f"ix_protocol_exports_{column}", "protocol_exports", [column])


def downgrade() -> None:
    op.drop_table("protocol_exports")
    op.drop_table("lab_protocol_wells")
    op.drop_table("lab_protocol_objects")
    op.drop_table("lab_protocol_stage_performers")
    op.drop_table("lab_protocol_stages")
    op.drop_table("lab_protocols")
    op.drop_table("protocol_stage_profiles")
