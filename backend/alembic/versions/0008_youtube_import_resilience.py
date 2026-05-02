"""youtube import resilience

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-13 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE video_source_type ADD VALUE IF NOT EXISTS 'youtube_single'")
    op.execute("ALTER TYPE video_source_type ADD VALUE IF NOT EXISTS 'youtube_playlist'")
    op.execute("ALTER TYPE video_source_type ADD VALUE IF NOT EXISTS 'youtube'")
    # PostgreSQL requires committing after adding enum values before using them.
    op.execute("COMMIT")
    op.execute(
        "UPDATE videos SET source_type='youtube_single'::video_source_type "
        "WHERE source_type='youtube'::video_source_type"
    )

    video_import_mode = sa.Enum(
        "server_download",
        "embed_only",
        "manual_upload",
        name="video_import_mode",
    )
    video_import_mode.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "youtube_playlist_imports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("playlist_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_youtube_playlist_imports_user_id", "youtube_playlist_imports", ["user_id"])
    op.create_index("ix_youtube_playlist_imports_status", "youtube_playlist_imports", ["status"])
    op.create_index("ix_youtube_playlist_imports_playlist_id", "youtube_playlist_imports", ["playlist_id"])

    op.add_column("videos", sa.Column("source_video_id", sa.String(length=32), nullable=True))
    op.add_column("videos", sa.Column("source_playlist_id", sa.String(length=64), nullable=True))
    op.add_column("videos", sa.Column("source_playlist_title", sa.String(length=500), nullable=True))
    op.add_column("videos", sa.Column("playlist_index", sa.Integer(), nullable=True))
    op.add_column("videos", sa.Column("import_parent_id", UUID(as_uuid=True), nullable=True))
    op.add_column("videos", sa.Column("embed_url", sa.Text(), nullable=True))
    op.add_column("videos", sa.Column("thumbnail_url", sa.Text(), nullable=True))
    op.add_column(
        "videos",
        sa.Column(
            "import_mode",
            sa.Enum(
                "server_download",
                "embed_only",
                "manual_upload",
                name="video_import_mode",
                create_type=False,
            ),
            nullable=False,
            server_default="server_download",
        ),
    )
    op.add_column(
        "videos",
        sa.Column("is_download_blocked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("videos", sa.Column("error_code", sa.String(length=64), nullable=True))
    op.add_column("videos", sa.Column("debug_error_message", sa.Text(), nullable=True))
    op.add_column(
        "videos",
        sa.Column("external_metadata_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

    op.create_index("ix_videos_source_video_id", "videos", ["source_video_id"])
    op.create_index("ix_videos_source_playlist_id", "videos", ["source_playlist_id"])
    op.create_index("ix_videos_playlist_index", "videos", ["playlist_index"])
    op.create_index("ix_videos_import_parent_id", "videos", ["import_parent_id"])

    op.create_foreign_key(
        "fk_videos_import_parent_id_youtube_playlist_imports",
        "videos",
        "youtube_playlist_imports",
        ["import_parent_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.alter_column("videos", "import_mode", server_default=None)
    op.alter_column("videos", "is_download_blocked", server_default=None)
    op.alter_column("videos", "external_metadata_json", server_default=None)


def downgrade() -> None:
    op.drop_constraint("fk_videos_import_parent_id_youtube_playlist_imports", "videos", type_="foreignkey")
    op.drop_index("ix_videos_import_parent_id", table_name="videos")
    op.drop_index("ix_videos_playlist_index", table_name="videos")
    op.drop_index("ix_videos_source_playlist_id", table_name="videos")
    op.drop_index("ix_videos_source_video_id", table_name="videos")

    op.drop_column("videos", "external_metadata_json")
    op.drop_column("videos", "debug_error_message")
    op.drop_column("videos", "error_code")
    op.drop_column("videos", "is_download_blocked")
    op.drop_column("videos", "import_mode")
    op.drop_column("videos", "thumbnail_url")
    op.drop_column("videos", "embed_url")
    op.drop_column("videos", "import_parent_id")
    op.drop_column("videos", "playlist_index")
    op.drop_column("videos", "source_playlist_title")
    op.drop_column("videos", "source_playlist_id")
    op.drop_column("videos", "source_video_id")

    op.drop_index("ix_youtube_playlist_imports_playlist_id", table_name="youtube_playlist_imports")
    op.drop_index("ix_youtube_playlist_imports_status", table_name="youtube_playlist_imports")
    op.drop_index("ix_youtube_playlist_imports_user_id", table_name="youtube_playlist_imports")
    op.drop_table("youtube_playlist_imports")

    sa.Enum(name="video_import_mode").drop(op.get_bind(), checkfirst=True)
