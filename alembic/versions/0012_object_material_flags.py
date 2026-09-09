"""Add persistent object material flags.

Revision ID: 0012_object_material_flags
Revises: 0011_electro_controls
Create Date: 2026-08-13
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_object_material_flags"
down_revision = "0011_electro_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("objects", sa.Column("empty_envelope", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("objects", sa.Column("is_consumed", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("objects", sa.Column("novosib", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.execute(
        """
        UPDATE objects
        SET empty_envelope = true,
            object_description = CASE
                WHEN lower(btrim(coalesce(object_description, ''))) = 'нет биоматериала' THEN 'Пустой конверт'
                ELSE object_description
            END
        WHERE lower(coalesce(object_description, '')) LIKE '%нет биоматериала%'
           OR lower(coalesce(object_description, '')) LIKE '%пустой конверт%'
        """
    )


def downgrade() -> None:
    op.drop_column("objects", "novosib")
    op.drop_column("objects", "is_consumed")
    op.drop_column("objects", "empty_envelope")
