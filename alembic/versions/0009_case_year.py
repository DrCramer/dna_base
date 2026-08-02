"""Add case year context for parties and objects.

Revision ID: 0009_case_year
Revises: 0008_repeat_objects
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_case_year"
down_revision = "0008_repeat_objects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("parties", sa.Column("case_year", sa.Integer(), nullable=True))
    op.add_column("objects", sa.Column("case_year", sa.Integer(), nullable=True))

    op.execute("""
        UPDATE objects
           SET case_year = COALESCE(
               NULLIF(substring(decree_no from '((19|20|21)[0-9]{2})$'), '')::integer,
               EXTRACT(YEAR FROM decision_date)::integer,
               2026
           )
    """)
    op.execute("""
        WITH object_years AS (
            SELECT party_id, case_year, COUNT(*) AS objects_count, MAX(id) AS max_object_id
              FROM objects
             WHERE party_id IS NOT NULL AND case_year IS NOT NULL
             GROUP BY party_id, case_year
        ), ranked AS (
            SELECT party_id, case_year,
                   ROW_NUMBER() OVER (PARTITION BY party_id ORDER BY objects_count DESC, max_object_id DESC) AS rn
              FROM object_years
        )
        UPDATE parties p
           SET case_year = ranked.case_year
          FROM ranked
         WHERE ranked.party_id = p.id AND ranked.rn = 1
    """)
    op.execute("UPDATE parties SET case_year = 2026 WHERE case_year IS NULL")
    op.execute("UPDATE objects o SET case_year = p.case_year FROM parties p WHERE o.party_id = p.id AND o.case_year IS NULL")
    op.execute("UPDATE objects SET case_year = 2026 WHERE case_year IS NULL")

    op.alter_column("parties", "case_year", nullable=False)
    op.alter_column("objects", "case_year", nullable=False)

    op.drop_index("ix_parties_party_no", table_name="parties")
    op.create_index("ix_parties_party_no", "parties", ["party_no"], unique=False)
    op.create_unique_constraint("uq_parties_case_year_party_no", "parties", ["case_year", "party_no"])

    op.drop_constraint("uq_objects_rcsme_reg_no", "objects", type_="unique")
    op.create_unique_constraint("uq_objects_case_year_rcsme_reg_no", "objects", ["case_year", "rcsme_reg_no"])
    op.create_unique_constraint("uq_objects_case_year_party_rcsme", "objects", ["case_year", "party_no", "rcsme_reg_no"])
    op.create_index("ix_objects_case_year", "objects", ["case_year"])


def downgrade() -> None:
    op.drop_index("ix_objects_case_year", table_name="objects")
    op.drop_constraint("uq_objects_case_year_party_rcsme", "objects", type_="unique")
    op.drop_constraint("uq_objects_case_year_rcsme_reg_no", "objects", type_="unique")
    op.create_unique_constraint("uq_objects_rcsme_reg_no", "objects", ["rcsme_reg_no"])

    op.drop_constraint("uq_parties_case_year_party_no", "parties", type_="unique")
    op.drop_index("ix_parties_party_no", table_name="parties")
    op.create_index("ix_parties_party_no", "parties", ["party_no"], unique=True)

    op.drop_column("objects", "case_year")
    op.drop_column("parties", "case_year")
