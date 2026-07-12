"""add official source workflow posts

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


source_status = postgresql.ENUM(
    "detected",
    "importing",
    "imported_processing",
    "ready_to_publish",
    "publishing",
    "completed",
    "original_required",
    "import_failed",
    "partial_failed",
    name="social_workflow_source_status",
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE video_source_type ADD VALUE IF NOT EXISTS 'instagram'")

    source_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "social_workflow_source_posts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_platform", postgresql.ENUM(name="social_platform", create_type=False), nullable=False),
        sa.Column("external_post_id", sa.String(length=255), nullable=False),
        sa.Column("permalink", sa.Text(), nullable=True),
        sa.Column("caption_snapshot", sa.Text(), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", postgresql.ENUM(name="social_workflow_source_status", create_type=False), nullable=False, server_default="detected"),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("export_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("workflow_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("raw_metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["export_id"], ["exports.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_account_id"], ["connected_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workflow_id"], ["social_workflows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["social_workflow_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_id", "source_platform", "external_post_id", name="uq_social_workflow_source_post_external"),
    )
    op.create_index("ix_social_workflow_source_posts_user_id", "social_workflow_source_posts", ["user_id"])
    op.create_index("ix_social_workflow_source_posts_workflow_id", "social_workflow_source_posts", ["workflow_id"])
    op.create_index("ix_social_workflow_source_posts_source_account_id", "social_workflow_source_posts", ["source_account_id"])
    op.create_index("ix_social_workflow_source_posts_source_platform", "social_workflow_source_posts", ["source_platform"])
    op.create_index("ix_social_workflow_source_posts_published_at", "social_workflow_source_posts", ["published_at"])
    op.create_index("ix_social_workflow_source_posts_status", "social_workflow_source_posts", ["status"])
    op.create_index("ix_social_workflow_source_posts_video_id", "social_workflow_source_posts", ["video_id"])
    op.create_index("ix_social_workflow_source_posts_export_id", "social_workflow_source_posts", ["export_id"])
    op.create_index("ix_social_workflow_source_posts_workflow_run_id", "social_workflow_source_posts", ["workflow_run_id"])

    op.add_column("publish_jobs", sa.Column("workflow_source_post_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_publish_jobs_workflow_source_post",
        "publish_jobs",
        "social_workflow_source_posts",
        ["workflow_source_post_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_publish_jobs_workflow_source_post_id", "publish_jobs", ["workflow_source_post_id"])
    op.create_index(
        "uq_publish_jobs_workflow_source_destination",
        "publish_jobs",
        ["workflow_source_post_id", "connected_account_id"],
        unique=True,
        postgresql_where=sa.text("workflow_source_post_id IS NOT NULL AND connected_account_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_publish_jobs_workflow_source_destination", table_name="publish_jobs")
    op.drop_index("ix_publish_jobs_workflow_source_post_id", table_name="publish_jobs")
    op.drop_constraint("fk_publish_jobs_workflow_source_post", "publish_jobs", type_="foreignkey")
    op.drop_column("publish_jobs", "workflow_source_post_id")
    op.drop_index("ix_social_workflow_source_posts_workflow_run_id", table_name="social_workflow_source_posts")
    op.drop_index("ix_social_workflow_source_posts_export_id", table_name="social_workflow_source_posts")
    op.drop_index("ix_social_workflow_source_posts_video_id", table_name="social_workflow_source_posts")
    op.drop_index("ix_social_workflow_source_posts_status", table_name="social_workflow_source_posts")
    op.drop_index("ix_social_workflow_source_posts_published_at", table_name="social_workflow_source_posts")
    op.drop_index("ix_social_workflow_source_posts_source_platform", table_name="social_workflow_source_posts")
    op.drop_index("ix_social_workflow_source_posts_source_account_id", table_name="social_workflow_source_posts")
    op.drop_index("ix_social_workflow_source_posts_workflow_id", table_name="social_workflow_source_posts")
    op.drop_index("ix_social_workflow_source_posts_user_id", table_name="social_workflow_source_posts")
    op.drop_table("social_workflow_source_posts")
    source_status.drop(op.get_bind(), checkfirst=True)
    # The video_source_type enum value is intentionally retained for safe downgrade.
