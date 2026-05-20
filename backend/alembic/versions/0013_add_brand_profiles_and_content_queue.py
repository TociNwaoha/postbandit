"""add brand profiles and content queue

Revision ID: 0013_brand_profiles_queue
Revises: 0012_add_carousel_exports
Create Date: 2026-05-20 09:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0013_brand_profiles_queue"
down_revision = "0012_add_carousel_exports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "brand_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("handle", sa.String(length=100), nullable=False),
        sa.Column("niche", sa.String(length=200), nullable=False),
        sa.Column("target_audience", sa.String(length=300), nullable=False),
        sa.Column("tone", sa.String(length=50), nullable=False),
        sa.Column("use_phrases", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("avoid_phrases", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("post_frequency", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("preferred_platforms", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_brand_profiles_user_id", "brand_profiles", ["user_id"], unique=True)

    op.create_table(
        "content_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=False, server_default="carousel"),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("slide_urls", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("platforms", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generation_topic", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_content_queue_user_id", "content_queue", ["user_id"], unique=False)
    op.create_index("ix_content_queue_status", "content_queue", ["status"], unique=False)
    op.create_index("ix_content_queue_created_at", "content_queue", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_content_queue_created_at", table_name="content_queue")
    op.drop_index("ix_content_queue_status", table_name="content_queue")
    op.drop_index("ix_content_queue_user_id", table_name="content_queue")
    op.drop_table("content_queue")

    op.drop_index("ix_brand_profiles_user_id", table_name="brand_profiles")
    op.drop_table("brand_profiles")
