"""reference items for laboratory dictionaries

Revision ID: 0005_reference_items
Revises: 0004_stage_table_realtime
Create Date: 2026-06-28
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_reference_items"
down_revision: Union[str, None] = "0004_stage_table_realtime"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEED_ITEMS = [
    ("pipetting_method", "ручной метод", "ручной"),
    ("pipetting_method", "робот", "робот"),
    ("pipetting_method", "Not applicable", "NA"),
    ("analysis_status", "не анализировался", None),
    ("analysis_status", "в работе", None),
    ("analysis_status", "получен генотип", None),
    ("analysis_status", "требуется повтор", None),
    ("analysis_status", "неудачно", None),
    ("analysis_status", "спорный результат", None),
    ("analysis_status", "завершено", None),
    ("extraction_method", "органический", None),
    ("extraction_method", "PrepFiler", None),
    ("quant_method", "Quantifiler Trio", None),
    ("pcr_panel", "GlobalFiler", None),
    ("sequencer", "3500 Genetic Analyzer", "3500"),
]


def upgrade() -> None:
    op.create_table(
        "reference_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("short_name", sa.String(120), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("category", "name", name="uq_reference_items_category_name"),
    )
    op.create_index("ix_reference_items_category", "reference_items", ["category"])
    op.create_index("ix_reference_items_name", "reference_items", ["name"])
    op.create_index("ix_reference_items_is_active", "reference_items", ["is_active"])
    bind = op.get_bind()
    for category, name, short_name in SEED_ITEMS:
        bind.execute(
            sa.text(
                """
                INSERT INTO reference_items (category, name, short_name, is_active)
                VALUES (:category, :name, :short_name, true)
                ON CONFLICT (category, name) DO NOTHING
                """
            ),
            {"category": category, "name": name, "short_name": short_name},
        )


def downgrade() -> None:
    op.drop_index("ix_reference_items_is_active", table_name="reference_items")
    op.drop_index("ix_reference_items_name", table_name="reference_items")
    op.drop_index("ix_reference_items_category", table_name="reference_items")
    op.drop_table("reference_items")
