"""add content queue asset tracking

Revision ID: 0030
Revises: 0029
Create Date: 2026-07-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_queue",
        sa.Column(
            "slide_keys_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column("content_queue", sa.Column("zip_key", sa.Text(), nullable=True))
    op.add_column("content_queue", sa.Column("preview_key", sa.Text(), nullable=True))
    op.add_column("content_queue", sa.Column("asset_cleanup_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("content_queue", sa.Column("assets_deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_content_queue_asset_cleanup_at", "content_queue", ["asset_cleanup_at"])


def downgrade() -> None:
    op.drop_index("ix_content_queue_asset_cleanup_at", table_name="content_queue")
    op.drop_column("content_queue", "assets_deleted_at")
    op.drop_column("content_queue", "asset_cleanup_at")
    op.drop_column("content_queue", "preview_key")
    op.drop_column("content_queue", "zip_key")
    op.drop_column("content_queue", "slide_keys_json")
