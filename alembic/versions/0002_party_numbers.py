"""add party numbers

Revision ID: 0002_party_numbers
Revises: 0001_initial
Create Date: 2026-06-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_party_numbers"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("registry_import_batches", sa.Column("party_no", sa.String(80), nullable=True))
    op.add_column("objects", sa.Column("party_no", sa.String(80), nullable=True))
    op.create_index("ix_registry_import_batches_party_no", "registry_import_batches", ["party_no"])
    op.create_index("ix_objects_party_no", "objects", ["party_no"])


def downgrade() -> None:
    op.drop_index("ix_objects_party_no", table_name="objects")
    op.drop_index("ix_registry_import_batches_party_no", table_name="registry_import_batches")
    op.drop_column("objects", "party_no")
    op.drop_column("registry_import_batches", "party_no")
