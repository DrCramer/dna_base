"""repeat objects and safe object archive

Revision ID: 0008_repeat_objects
Revises: 0007_rt_quantities_pdf_files
Create Date: 2026-07-07
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_repeat_objects"
down_revision: Union[str, None] = "0007_rt_quantities_pdf_files"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("objects", sa.Column("parent_object_id", sa.Integer(), nullable=True))
    op.add_column("objects", sa.Column("repeat_suffix", sa.String(length=32), nullable=True))
    op.create_foreign_key(
        "fk_objects_parent_object_id_objects",
        "objects",
        "objects",
        ["parent_object_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_objects_parent_object_id", "objects", ["parent_object_id"])
    op.create_index("ix_objects_repeat_suffix", "objects", ["repeat_suffix"])
    op.create_index("ix_objects_repeat_lookup", "objects", ["party_id", "parent_object_id", "repeat_suffix"])

    op.execute(
        """
        WITH repeat_candidates AS (
            SELECT
                child.id AS child_id,
                parent.id AS parent_id,
                lower(replace(substring(child.rcsme_reg_no from '^[0-9]+-[0-9]+(.+)$'), 'х', 'x')) AS suffix
            FROM objects child
            JOIN objects parent
              ON parent.party_id IS NOT DISTINCT FROM child.party_id
             AND parent.rcsme_reg_no = substring(child.rcsme_reg_no from '^([0-9]+-[0-9]+).+$')
            WHERE child.rcsme_reg_no ~ '^[0-9]+-[0-9]+[A-Za-zА-Яа-я*]+$'
              AND child.parent_object_id IS NULL
        )
        UPDATE objects target
           SET parent_object_id = repeat_candidates.parent_id,
               repeat_suffix = repeat_candidates.suffix
          FROM repeat_candidates
         WHERE target.id = repeat_candidates.child_id
        """
    )


def downgrade() -> None:
    op.drop_index("ix_objects_repeat_lookup", table_name="objects")
    op.drop_index("ix_objects_repeat_suffix", table_name="objects")
    op.drop_index("ix_objects_parent_object_id", table_name="objects")
    op.drop_constraint("fk_objects_parent_object_id_objects", "objects", type_="foreignkey")
    op.drop_column("objects", "repeat_suffix")
    op.drop_column("objects", "parent_object_id")
