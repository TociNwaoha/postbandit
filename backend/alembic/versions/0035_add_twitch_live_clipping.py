"""add Twitch live clipping models

Revision ID: 0035
Revises: 0034
Create Date: 2026-08-15 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE video_source_type ADD VALUE IF NOT EXISTS 'twitch_live'")
    op.create_table(
        "twitch_channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("twitch_broadcaster_id", sa.String(length=64), nullable=False),
        sa.Column("twitch_login", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("is_live", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_live_event_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Enum("active", "disconnected", name="twitch_channel_status"), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_user_id", "twitch_broadcaster_id", name="uq_twitch_channel_owner_broadcaster"),
    )
    op.create_index("ix_twitch_channels_owner_user_id", "twitch_channels", ["owner_user_id"])
    op.create_index("ix_twitch_channels_twitch_broadcaster_id", "twitch_channels", ["twitch_broadcaster_id"])
    op.create_index("ix_twitch_channels_is_live", "twitch_channels", ["is_live"])
    op.create_table(
        "twitch_service_credentials",
        sa.Column("key", sa.String(length=32), primary_key=True),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_token_refresh", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("videos", sa.Column("twitch_clip_id", sa.String(length=128)))
    op.add_column("videos", sa.Column("twitch_clip_slug", sa.String(length=255)))
    op.add_column("videos", sa.Column("triggering_channel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("twitch_channels.id", ondelete="SET NULL")))
    op.add_column("videos", sa.Column("triggered_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")))
    op.create_index("ix_videos_twitch_clip_id", "videos", ["twitch_clip_id"])
    op.create_index("ix_videos_triggering_channel_id", "videos", ["triggering_channel_id"])
    op.create_index("ix_videos_triggered_by_user_id", "videos", ["triggered_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_videos_triggered_by_user_id", table_name="videos")
    op.drop_index("ix_videos_triggering_channel_id", table_name="videos")
    op.drop_index("ix_videos_twitch_clip_id", table_name="videos")
    op.drop_column("videos", "triggered_by_user_id")
    op.drop_column("videos", "triggering_channel_id")
    op.drop_column("videos", "twitch_clip_slug")
    op.drop_column("videos", "twitch_clip_id")
    op.drop_table("twitch_service_credentials")
    op.drop_index("ix_twitch_channels_is_live", table_name="twitch_channels")
    op.drop_index("ix_twitch_channels_twitch_broadcaster_id", table_name="twitch_channels")
    op.drop_index("ix_twitch_channels_owner_user_id", table_name="twitch_channels")
    op.drop_table("twitch_channels")
    op.execute("DROP TYPE IF EXISTS twitch_channel_status")
