"""add social cross-post workflows

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-14 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    copy_mode = postgresql.ENUM("ai_platform", "reuse_source", name="workflow_copy_mode")
    run_status = postgresql.ENUM(
        "waiting_asset",
        "processing",
        "queued",
        "completed",
        "partial_failed",
        "failed",
        "skipped",
        name="workflow_run_status",
    )
    copy_mode.create(op.get_bind(), checkfirst=True)
    run_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "social_workflows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_platform", postgresql.ENUM(name="social_platform", create_type=False), nullable=False),
        sa.Column("copy_mode", postgresql.ENUM(name="workflow_copy_mode", create_type=False), nullable=False),
        sa.Column("destination_configs", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("cursor_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_account_id"], ["connected_accounts.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_social_workflows_user_id", "social_workflows", ["user_id"])
    op.create_index("ix_social_workflows_source_account_id", "social_workflows", ["source_account_id"])
    op.create_index("ix_social_workflows_source_platform", "social_workflows", ["source_platform"])
    op.create_index("ix_social_workflows_enabled", "social_workflows", ["enabled"])

    op.create_table(
        "social_workflow_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_publish_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_export_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_platform", postgresql.ENUM(name="social_platform", create_type=False), nullable=False),
        sa.Column("source_external_post_id", sa.String(length=255), nullable=False),
        sa.Column("source_external_url", sa.Text(), nullable=True),
        sa.Column("source_title", sa.String(length=500), nullable=True),
        sa.Column("source_description", sa.Text(), nullable=True),
        sa.Column("source_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", postgresql.ENUM(name="workflow_run_status", create_type=False), nullable=False),
        sa.Column("generated_copy_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workflow_id"], ["social_workflows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_publish_job_id"], ["publish_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_export_id"], ["exports.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("workflow_id", "source_external_post_id", name="uq_workflow_source_post"),
    )
    op.create_index("ix_social_workflow_runs_workflow_id", "social_workflow_runs", ["workflow_id"])
    op.create_index("ix_social_workflow_runs_user_id", "social_workflow_runs", ["user_id"])
    op.create_index("ix_social_workflow_runs_status", "social_workflow_runs", ["status"])
    op.create_index("ix_social_workflow_runs_source_publish_job_id", "social_workflow_runs", ["source_publish_job_id"])
    op.create_index("ix_social_workflow_runs_source_export_id", "social_workflow_runs", ["source_export_id"])

    op.add_column(
        "publish_jobs",
        sa.Column("workflow_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_publish_jobs_workflow_run_id",
        "publish_jobs",
        "social_workflow_runs",
        ["workflow_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_publish_jobs_workflow_run_id", "publish_jobs", ["workflow_run_id"])


def downgrade() -> None:
    op.drop_index("ix_publish_jobs_workflow_run_id", table_name="publish_jobs")
    op.drop_constraint("fk_publish_jobs_workflow_run_id", "publish_jobs", type_="foreignkey")
    op.drop_column("publish_jobs", "workflow_run_id")
    op.drop_table("social_workflow_runs")
    op.drop_table("social_workflows")
    postgresql.ENUM(name="workflow_run_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="workflow_copy_mode").drop(op.get_bind(), checkfirst=True)
