"""export library and clip copy fields

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-03 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clips", sa.Column("title_options", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("clips", sa.Column("hashtag_options", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("clips", sa.Column("copy_generation_status", sa.String(length=32), nullable=True))
    op.add_column("clips", sa.Column("copy_generation_error", sa.Text(), nullable=True))

    op.add_column("exports", sa.Column("retry_of_export_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_exports_retry_of_export_id_exports",
        "exports",
        "exports",
        ["retry_of_export_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_exports_retry_of_export_id", "exports", ["retry_of_export_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_exports_retry_of_export_id", table_name="exports")
    op.drop_constraint("fk_exports_retry_of_export_id_exports", "exports", type_="foreignkey")
    op.drop_column("exports", "retry_of_export_id")

    op.drop_column("clips", "copy_generation_error")
    op.drop_column("clips", "copy_generation_status")
    op.drop_column("clips", "hashtag_options")
    op.drop_column("clips", "title_options")
