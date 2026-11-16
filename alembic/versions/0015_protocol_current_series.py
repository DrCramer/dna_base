"""Protect the single current revision without removing historical documents."""

from alembic import op
import sqlalchemy as sa

revision = "0015_protocol_current_series"
down_revision = "0014_genetic_examinations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("LOCK TABLE lab_protocols IN SHARE ROW EXCLUSIVE MODE"))
    op.execute(sa.text("""
        WITH ranked AS (
            SELECT id, row_number() OVER (
                PARTITION BY series_key ORDER BY revision_no DESC, id DESC
            ) AS position
            FROM lab_protocols WHERE is_current
        )
        UPDATE lab_protocols SET is_current = false
        FROM ranked WHERE lab_protocols.id = ranked.id AND ranked.position > 1
    """))
    op.create_index("uq_lab_protocols_current_series", "lab_protocols", ["series_key"], unique=True, postgresql_where=sa.text("is_current"))


def downgrade() -> None:
    op.drop_index("uq_lab_protocols_current_series", table_name="lab_protocols")
