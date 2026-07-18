"""social distribution foundation

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-08 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PGEnum, JSONB, UUID

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    social_platform = PGEnum(
        "instagram",
        "tiktok",
        "facebook",
        "youtube",
        "x",
        "linkedin",
        name="social_platform",
    )
    social_platform_no_create = PGEnum(
        "instagram",
        "tiktok",
        "facebook",
        "youtube",
        "x",
        "linkedin",
        name="social_platform",
        create_type=False,
    )
    publish_status = PGEnum(
        "queued",
        "publishing",
        "published",
        "failed",
        "waiting_user_action",
        "provider_not_configured",
        name="publish_status",
    )
    publish_status_no_create = PGEnum(
        "queued",
        "publishing",
        "published",
        "failed",
        "waiting_user_action",
        "provider_not_configured",
        name="publish_status",
        create_type=False,
    )
    publish_mode = PGEnum("now", "scheduled", name="publish_mode")
    publish_mode_no_create = PGEnum("now", "scheduled", name="publish_mode", create_type=False)

    bind = op.get_bind()
    social_platform.create(bind, checkfirst=True)
    publish_status.create(bind, checkfirst=True)
    publish_mode.create(bind, checkfirst=True)

    op.create_table(
        "connected_accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", social_platform_no_create, nullable=False),
        sa.Column("external_account_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("username_or_channel_name", sa.String(length=255), nullable=True),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", JSONB, nullable=True),
        sa.Column("metadata_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "platform", "external_account_id", name="uq_connected_account_user_platform_external"),
    )
    op.create_index("ix_connected_accounts_user_id", "connected_accounts", ["user_id"])
    op.create_index("ix_connected_accounts_platform", "connected_accounts", ["platform"])

    op.create_table(
        "publish_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("export_id", UUID(as_uuid=True), sa.ForeignKey("exports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clip_id", UUID(as_uuid=True), sa.ForeignKey("clips.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", social_platform_no_create, nullable=False),
        sa.Column(
            "connected_account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("connected_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", publish_status_no_create, nullable=False, server_default="queued"),
        sa.Column("publish_mode", publish_mode_no_create, nullable=False, server_default="now"),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("hashtags", JSONB, nullable=True),
        sa.Column("privacy", sa.String(length=64), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_post_id", sa.String(length=255), nullable=True),
        sa.Column("external_post_url", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("provider_metadata_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_publish_jobs_user_id", "publish_jobs", ["user_id"])
    op.create_index("ix_publish_jobs_export_id", "publish_jobs", ["export_id"])
    op.create_index("ix_publish_jobs_clip_id", "publish_jobs", ["clip_id"])
    op.create_index("ix_publish_jobs_platform", "publish_jobs", ["platform"])
    op.create_index("ix_publish_jobs_connected_account_id", "publish_jobs", ["connected_account_id"])
    op.create_index("ix_publish_jobs_status", "publish_jobs", ["status"])
    op.create_index("ix_publish_jobs_scheduled_for", "publish_jobs", ["scheduled_for"])

    op.create_table(
        "publish_attempts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "publish_job_id",
            UUID(as_uuid=True),
            sa.ForeignKey("publish_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("request_payload_json", JSONB, nullable=True),
        sa.Column("response_payload_json", JSONB, nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_publish_attempts_publish_job_id", "publish_attempts", ["publish_job_id"])


def downgrade() -> None:
    op.drop_index("ix_publish_attempts_publish_job_id", table_name="publish_attempts")
    op.drop_table("publish_attempts")

    op.drop_index("ix_publish_jobs_scheduled_for", table_name="publish_jobs")
    op.drop_index("ix_publish_jobs_status", table_name="publish_jobs")
    op.drop_index("ix_publish_jobs_connected_account_id", table_name="publish_jobs")
    op.drop_index("ix_publish_jobs_platform", table_name="publish_jobs")
    op.drop_index("ix_publish_jobs_clip_id", table_name="publish_jobs")
    op.drop_index("ix_publish_jobs_export_id", table_name="publish_jobs")
    op.drop_index("ix_publish_jobs_user_id", table_name="publish_jobs")
    op.drop_table("publish_jobs")

    op.drop_index("ix_connected_accounts_platform", table_name="connected_accounts")
    op.drop_index("ix_connected_accounts_user_id", table_name="connected_accounts")
    op.drop_table("connected_accounts")

    bind = op.get_bind()
    sa.Enum(name="publish_mode").drop(bind, checkfirst=True)
    sa.Enum(name="publish_status").drop(bind, checkfirst=True)
    sa.Enum(name="social_platform").drop(bind, checkfirst=True)
