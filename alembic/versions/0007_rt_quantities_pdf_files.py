"""rt target quantities and electrophoresis files

Revision ID: 0007_rt_quantities_pdf_files
Revises: 0006_employee_stage_roles
Create Date: 2026-07-05
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_rt_quantities_pdf_files"
down_revision: Union[str, None] = "0006_employee_stage_roles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("realtime_details", sa.Column("long_quantity", sa.Float(), nullable=True))
    op.add_column("realtime_details", sa.Column("small_quantity", sa.Float(), nullable=True))
    op.add_column("realtime_details", sa.Column("y_quantity", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("realtime_details", "y_quantity")
    op.drop_column("realtime_details", "small_quantity")
    op.drop_column("realtime_details", "long_quantity")
