"""employee stage roles and dictionary backfill

Revision ID: 0006_employee_stage_roles
Revises: 0005_reference_items
Create Date: 2026-06-29
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_employee_stage_roles"
down_revision: Union[str, None] = "0005_reference_items"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "employee_stage_roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_type", sa.String(80), nullable=False),
        sa.Column("role", sa.String(120), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("employee_id", "stage_type", name="uq_employee_stage_roles_once"),
    )
    op.create_index("ix_employee_stage_roles_employee_id", "employee_stage_roles", ["employee_id"])
    op.create_index("ix_employee_stage_roles_stage_type", "employee_stage_roles", ["stage_type"])
    op.create_index("ix_employee_stage_roles_role", "employee_stage_roles", ["role"])
    op.create_index("ix_employee_stage_roles_is_active", "employee_stage_roles", ["is_active"])

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE milling_details
            SET cups = trim(split_part(stage_events.comment, ':', 2))
            FROM stage_events
            WHERE milling_details.stage_event_id = stage_events.id
              AND (milling_details.cups IS NULL OR milling_details.cups = '')
              AND stage_events.comment ILIKE 'стакан%:%'
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE stage_events
            SET comment = NULL
            FROM milling_details
            WHERE milling_details.stage_event_id = stage_events.id
              AND milling_details.cups IS NOT NULL
              AND stage_events.comment ILIKE 'стакан%:%'
            """
        )
    )
    for category, table, column_name in [
        ("extraction_method", "dna_extraction_details", "extraction_method"),
        ("quant_method", "realtime_details", "quant_method"),
        ("pipetting_method", "realtime_details", "pipetting_method"),
        ("pipetting_method", "pcr_details", "pipetting_method"),
        ("pipetting_method", "electrophoresis_details", "pipetting_method"),
        ("pcr_panel", "pcr_details", "locus_panel"),
        ("sequencer", "electrophoresis_details", "sequencer"),
        ("analysis_status", "analysis_details", "status"),
    ]:
        bind.execute(
            sa.text(
                f"""
                INSERT INTO reference_items (category, name, is_active)
                SELECT DISTINCT :category, trim({column_name}), true
                FROM {table}
                WHERE {column_name} IS NOT NULL AND trim({column_name}) <> ''
                ON CONFLICT (category, name) DO NOTHING
                """
            ),
            {"category": category},
        )


def downgrade() -> None:
    op.drop_index("ix_employee_stage_roles_is_active", table_name="employee_stage_roles")
    op.drop_index("ix_employee_stage_roles_role", table_name="employee_stage_roles")
    op.drop_index("ix_employee_stage_roles_stage_type", table_name="employee_stage_roles")
    op.drop_index("ix_employee_stage_roles_employee_id", table_name="employee_stage_roles")
    op.drop_table("employee_stage_roles")
