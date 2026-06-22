"""add social repurpose workflows

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


workflow_status = postgresql.ENUM("active", "paused", name="social_workflow_status")
copy_mode = postgresql.ENUM("reuse_source", "platform_ai", "both", name="social_workflow_copy_mode")
run_status = postgresql.ENUM(
    "detected",
    "importing",
    "imported_processing",
    "ready_to_publish",
    "publishing",
    "completed",
    "original_required",
    "import_failed",
    "partial_failed",
    name="social_workflow_run_status",
)


def upgrade() -> None:
    workflow_status.create(op.get_bind(), checkfirst=True)
    copy_mode.create(op.get_bind(), checkfirst=True)
    run_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "social_workflows",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_platform", postgresql.ENUM(name="social_platform", create_type=False), nullable=False),
        sa.Column("source_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", postgresql.ENUM(name="social_workflow_status", create_type=False), nullable=False, server_default="active"),
        sa.Column("copy_mode", postgresql.ENUM(name="social_workflow_copy_mode", create_type=False), nullable=False, server_default="both"),
        sa.Column("auto_publish", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("destination_targets_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("poll_cursor_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["source_account_id"], ["connected_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_workflows_user_id", "social_workflows", ["user_id"])
    op.create_index("ix_social_workflows_status", "social_workflows", ["status"])
    op.create_index("ix_social_workflows_source_platform", "social_workflows", ["source_platform"])
    op.create_index("ix_social_workflows_source_account_id", "social_workflows", ["source_account_id"])

    op.create_table(
        "social_workflow_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", postgresql.ENUM(name="social_workflow_run_status", create_type=False), nullable=False, server_default="detected"),
        sa.Column("publish_job_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("destination_results_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["social_workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_social_workflow_runs_user_id", "social_workflow_runs", ["user_id"])
    op.create_index("ix_social_workflow_runs_workflow_id", "social_workflow_runs", ["workflow_id"])
    op.create_index("ix_social_workflow_runs_status", "social_workflow_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_social_workflow_runs_status", table_name="social_workflow_runs")
    op.drop_index("ix_social_workflow_runs_workflow_id", table_name="social_workflow_runs")
    op.drop_index("ix_social_workflow_runs_user_id", table_name="social_workflow_runs")
    op.drop_table("social_workflow_runs")
    op.drop_index("ix_social_workflows_source_account_id", table_name="social_workflows")
    op.drop_index("ix_social_workflows_source_platform", table_name="social_workflows")
    op.drop_index("ix_social_workflows_status", table_name="social_workflows")
    op.drop_index("ix_social_workflows_user_id", table_name="social_workflows")
    op.drop_table("social_workflows")
    run_status.drop(op.get_bind(), checkfirst=True)
    copy_mode.drop(op.get_bind(), checkfirst=True)
    workflow_status.drop(op.get_bind(), checkfirst=True)
