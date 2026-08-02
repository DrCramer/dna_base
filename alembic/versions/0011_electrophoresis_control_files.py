"""Add electrophoresis control files.

Revision ID: 0011_electro_controls
Revises: 0010_prefer_decree_year
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa

from app.models.entities import json_type


revision = "0011_electro_controls"
down_revision = "0010_prefer_decree_year"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "electrophoresis_control_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("party_id", sa.Integer(), nullable=False),
        sa.Column("case_year", sa.Integer(), nullable=True),
        sa.Column("control_type", sa.String(length=40), nullable=False),
        sa.Column("control_label", sa.String(length=255), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("file_type", sa.String(length=80), nullable=True),
        sa.Column("analysis_date", sa.Date(), nullable=True),
        sa.Column("analysis_performer", sa.String(length=255), nullable=True),
        sa.Column("uploaded_by", sa.Integer(), nullable=True),
        sa.Column("raw_json", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["party_id"], ["parties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_electrophoresis_control_files_party_id", "electrophoresis_control_files", ["party_id"])
    op.create_index("ix_electrophoresis_control_files_case_year", "electrophoresis_control_files", ["case_year"])
    op.create_index("ix_electrophoresis_control_files_control_type", "electrophoresis_control_files", ["control_type"])
    op.create_index("ix_electrophoresis_control_files_filename", "electrophoresis_control_files", ["filename"])
    op.create_index("ix_electrophoresis_control_lookup", "electrophoresis_control_files", ["party_id", "control_type", "filename"])


def downgrade() -> None:
    op.drop_index("ix_electrophoresis_control_lookup", table_name="electrophoresis_control_files")
    op.drop_index("ix_electrophoresis_control_files_filename", table_name="electrophoresis_control_files")
    op.drop_index("ix_electrophoresis_control_files_control_type", table_name="electrophoresis_control_files")
    op.drop_index("ix_electrophoresis_control_files_case_year", table_name="electrophoresis_control_files")
    op.drop_index("ix_electrophoresis_control_files_party_id", table_name="electrophoresis_control_files")
    op.drop_table("electrophoresis_control_files")
