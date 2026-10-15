"""Independent genetic examinations and typed protocol sources."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0014_genetic_examinations"
down_revision = "0013_lab_protocols"
branch_labels = None
depends_on = None
json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def timestamps():
    return [sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()) for name in ("created_at", "updated_at")]


def upgrade() -> None:
    op.create_table("genetic_examinations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("examination_year", sa.Integer(), nullable=False),
        sa.Column("examination_no", sa.String(120), nullable=False),
        sa.Column("normalized_examination_no", sa.String(120), nullable=False),
        sa.Column("title", sa.String(255)), sa.Column("comment", sa.Text()),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        *timestamps(), sa.UniqueConstraint("examination_year", "normalized_examination_no", name="uq_genetic_examination_year_no"))
    op.create_table("genetic_examination_objects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("examination_id", sa.Integer(), sa.ForeignKey("genetic_examinations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("object_no_raw", sa.String(255), nullable=False),
        sa.Column("object_no_normalized", sa.String(255), nullable=False),
        sa.Column("object_index", sa.Integer()), sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()), sa.Column("comment", sa.Text()),
        sa.Column("order_index", sa.Integer(), nullable=False), *timestamps(),
        sa.UniqueConstraint("examination_id", "object_no_normalized", name="uq_genetic_object_examination_no"))
    op.create_table("genetic_examination_rt_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("examination_year", sa.Integer(), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=False), sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("run_date", sa.Date()), sa.Column("instrument", sa.String(255)), sa.Column("quant_method", sa.String(255)),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("imported_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("metadata_json", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table("genetic_examination_rt_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("genetic_examination_rt_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("genetic_examination_object_id", sa.Integer(), sa.ForeignKey("genetic_examination_objects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sample_name_raw", sa.String(255), nullable=False), sa.Column("normalized_sample_name", sa.String(255), nullable=False),
        sa.Column("target_key", sa.String(40), nullable=False), sa.Column("quantity", sa.Float()), sa.Column("ct_cq", sa.Float()),
        sa.Column("di", sa.Float()), sa.Column("well", sa.String(40)),
        sa.Column("raw_json", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_table("genetic_protocol_uploads",
        sa.Column("id", sa.String(80), primary_key=True), sa.Column("category", sa.String(40), nullable=False),
        sa.Column("examination_year", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=False), sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("parsed_json", json_type, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    for table, columns in {
        "genetic_examinations": ("examination_year", "normalized_examination_no"),
        "genetic_examination_objects": ("examination_id", "object_no_normalized"),
        "genetic_examination_rt_runs": ("examination_year", "sha256"),
        "genetic_examination_rt_results": ("run_id", "genetic_examination_object_id"),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.add_column("lab_protocols", sa.Column("kind", sa.String(40), nullable=False, server_default="chs"))
    op.create_index("ix_lab_protocols_kind", "lab_protocols", ["kind"])
    op.create_index("ix_lab_protocols_examination_year", "lab_protocols", [sa.text("CAST(snapshot_json->>'examination_year' AS INTEGER)")], postgresql_where=sa.text("kind = 'genetic_examination'"))
    op.drop_constraint("uq_lab_protocols_date_no_revision", "lab_protocols", type_="unique")
    op.create_unique_constraint("uq_lab_protocols_kind_date_no_revision", "lab_protocols", ["kind", "protocol_date", "protocol_no", "revision_no"])
    for table in ("lab_protocol_objects", "lab_protocol_wells"):
        op.add_column(table, sa.Column("genetic_examination_object_id", sa.Integer(), nullable=True))
        op.create_foreign_key(f"fk_{table}_genetic_object", table, "genetic_examination_objects", ["genetic_examination_object_id"], ["id"], ondelete="RESTRICT")
        op.create_index(f"ix_{table}_genetic_examination_object_id", table, ["genetic_examination_object_id"])
        op.create_check_constraint("ck_protocol_objects_source" if table.endswith("objects") else "ck_protocol_wells_source", table, "NOT (object_id IS NOT NULL AND genetic_examination_object_id IS NOT NULL)")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM lab_protocols WHERE kind <> 'chs') OR EXISTS (SELECT 1 FROM genetic_examinations) OR EXISTS (SELECT 1 FROM genetic_protocol_uploads)")).scalar():
        raise RuntimeError("Откат запрещён: сначала явно сохраните и перенесите генетические данные.")
    for table in ("lab_protocol_objects", "lab_protocol_wells"):
        op.drop_constraint("ck_protocol_objects_source" if table.endswith("objects") else "ck_protocol_wells_source", table, type_="check")
        op.drop_index(f"ix_{table}_genetic_examination_object_id", table_name=table)
        op.drop_constraint(f"fk_{table}_genetic_object", table, type_="foreignkey")
        op.drop_column(table, "genetic_examination_object_id")
    op.drop_constraint("uq_lab_protocols_kind_date_no_revision", "lab_protocols", type_="unique")
    op.create_unique_constraint("uq_lab_protocols_date_no_revision", "lab_protocols", ["protocol_date", "protocol_no", "revision_no"])
    op.drop_index("ix_lab_protocols_kind", table_name="lab_protocols")
    op.drop_index("ix_lab_protocols_examination_year", table_name="lab_protocols")
    op.drop_column("lab_protocols", "kind")
    for table in ("genetic_protocol_uploads", "genetic_examination_rt_results", "genetic_examination_rt_runs", "genetic_examination_objects", "genetic_examinations"):
        op.drop_table(table)
