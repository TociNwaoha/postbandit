"""youtube import state machine and transition events

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    video_import_state = sa.Enum(
        "not_applicable",
        "queued",
        "metadata_extracting",
        "downloadable",
        "downloading",
        "blocked",
        "replacement_upload_required",
        "helper_required",
        "embed_only",
        "processing",
        "ready",
        "failed_retryable",
        "failed_terminal",
        name="video_import_state",
    )
    video_import_state.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "videos",
        sa.Column(
            "import_state",
            sa.Enum(name="video_import_state", create_type=False),
            nullable=False,
            server_default="not_applicable",
        ),
    )
    op.add_column(
        "videos",
        sa.Column("import_state_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_videos_import_state", "videos", ["import_state"])

    op.execute(
        """
        UPDATE videos
        SET import_state = CASE
            WHEN source_type::text NOT IN ('youtube', 'youtube_single', 'youtube_playlist') THEN 'not_applicable'::video_import_state
            WHEN status::text = 'queued' THEN 'queued'::video_import_state
            WHEN status::text = 'downloading' THEN 'downloading'::video_import_state
            WHEN status::text IN ('transcribing', 'scoring') THEN 'processing'::video_import_state
            WHEN status::text = 'ready' THEN 'ready'::video_import_state
            WHEN status::text = 'error' AND COALESCE(is_download_blocked, false) = true THEN 'replacement_upload_required'::video_import_state
            WHEN status::text = 'error' THEN 'failed_retryable'::video_import_state
            ELSE 'not_applicable'::video_import_state
        END
        """
    )

    op.create_table(
        "video_import_state_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("video_id", UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_state", sa.String(length=64), nullable=True),
        sa.Column("to_state", sa.String(length=64), nullable=False),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False, server_default="system"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_video_import_state_events_video_id", "video_import_state_events", ["video_id"])
    op.create_index("ix_video_import_state_events_user_id", "video_import_state_events", ["user_id"])
    op.create_index("ix_video_import_state_events_created_at", "video_import_state_events", ["created_at"])

    op.alter_column("videos", "import_state", server_default=None)
    op.alter_column("videos", "import_state_version", server_default=None)
    op.alter_column("video_import_state_events", "actor", server_default=None)
    op.alter_column("video_import_state_events", "version", server_default=None)
    op.alter_column("video_import_state_events", "metadata_json", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_video_import_state_events_created_at", table_name="video_import_state_events")
    op.drop_index("ix_video_import_state_events_user_id", table_name="video_import_state_events")
    op.drop_index("ix_video_import_state_events_video_id", table_name="video_import_state_events")
    op.drop_table("video_import_state_events")

    op.drop_index("ix_videos_import_state", table_name="videos")
    op.drop_column("videos", "import_state_version")
    op.drop_column("videos", "import_state")
    sa.Enum(name="video_import_state").drop(op.get_bind(), checkfirst=True)
