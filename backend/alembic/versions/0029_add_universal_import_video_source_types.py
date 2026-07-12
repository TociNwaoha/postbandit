"""add universal import video source types

Revision ID: 0029_add_universal_import_video_source_types
Revises: 0028_add_post_analytics
Create Date: 2026-07-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0029_add_universal_import_video_source_types"
down_revision = "0028_add_post_analytics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("videos", "source_video_id", existing_type=sa.String(length=32), type_=sa.String(length=128), existing_nullable=True)
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    if dialect_name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE video_source_type ADD VALUE IF NOT EXISTS 'tiktok'")
            op.execute("ALTER TYPE video_source_type ADD VALUE IF NOT EXISTS 'x'")
            op.execute("ALTER TYPE video_source_type ADD VALUE IF NOT EXISTS 'twitch'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be safely removed while rows may reference them.
    op.alter_column("videos", "source_video_id", existing_type=sa.String(length=128), type_=sa.String(length=32), existing_nullable=True)
