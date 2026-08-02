"""Prefer decree year for case_year.

Revision ID: 0010_prefer_decree_year
Revises: 0009_case_year
Create Date: 2026-07-17
"""

from alembic import op


revision = "0010_prefer_decree_year"
down_revision = "0009_case_year"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE objects
           SET case_year = NULLIF(substring(decree_no from '((19|20|21)[0-9]{2})$'), '')::integer
         WHERE decree_no IS NOT NULL
           AND NULLIF(substring(decree_no from '((19|20|21)[0-9]{2})$'), '') IS NOT NULL
           AND case_year IS DISTINCT FROM NULLIF(substring(decree_no from '((19|20|21)[0-9]{2})$'), '')::integer
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
    op.execute("""
        UPDATE objects o
           SET case_year = p.case_year
          FROM parties p
         WHERE o.party_id = p.id
           AND o.decree_no IS NULL
           AND o.case_year IS DISTINCT FROM p.case_year
    """)


def downgrade() -> None:
    pass
