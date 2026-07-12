"""add post analytics

Revision ID: 0028
Revises: 0027
Create Date: 2026-07-10 22:35:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "post_analytics",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "publish_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publish_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("views", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("likes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("comments", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("shares", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("reach", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("impressions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("fetch_error", sa.String(length=100), nullable=True),
        sa.Column("raw_response", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_post_analytics_publish_job_id", "post_analytics", ["publish_job_id"], unique=True)
    op.create_index("ix_post_analytics_provider_fetched_at", "post_analytics", ["provider", "fetched_at"], unique=False)
    op.create_index("ix_post_analytics_views", "post_analytics", ["views"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_post_analytics_views", table_name="post_analytics")
    op.drop_index("ix_post_analytics_provider_fetched_at", table_name="post_analytics")
    op.drop_index("ix_post_analytics_publish_job_id", table_name="post_analytics")
    op.drop_table("post_analytics")
