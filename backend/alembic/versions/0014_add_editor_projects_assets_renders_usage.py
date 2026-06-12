"""add editor projects, assets, renders, and storage usage

Revision ID: 0014
Revises: 0013_brand_profiles_queue
Create Date: 2026-05-23 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0014"
down_revision = "0013_brand_profiles_queue"
branch_labels = None
depends_on = None


def _ensure_enum(name: str, values: list[str]) -> None:
    quoted = ", ".join(f"'{value}'" for value in values)
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{name}') THEN
                CREATE TYPE {name} AS ENUM ({quoted});
            END IF;
        END$$;
        """
    )


def upgrade() -> None:
    _ensure_enum("editor_project_status", ["draft", "rendering", "ready", "error", "archived"])
    _ensure_enum("editor_asset_type", ["image", "logo"])
    _ensure_enum("editor_render_status", ["queued", "processing", "completed", "failed"])
    _ensure_enum("editor_render_preset", ["tiktok", "reels", "shorts", "linkedin", "square", "landscape"])

    editor_project_status = postgresql.ENUM(name="editor_project_status", create_type=False)
    editor_asset_type = postgresql.ENUM(name="editor_asset_type", create_type=False)
    editor_render_status = postgresql.ENUM(name="editor_render_status", create_type=False)
    editor_render_preset = postgresql.ENUM(name="editor_render_preset", create_type=False)
    aspect_ratio = postgresql.ENUM(name="aspect_ratio", create_type=False)

    op.create_table(
        "editor_projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("clip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=True),
        sa.Column("status", editor_project_status, nullable=False, server_default="draft"),
        sa.Column("aspect_ratio", aspect_ratio, nullable=False, server_default="9:16"),
        sa.Column("trim_start_sec", sa.Float(), nullable=False, server_default="0"),
        sa.Column("trim_end_sec", sa.Float(), nullable=False, server_default="0"),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("project_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["clip_id"], ["clips.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_editor_projects_user_id"), "editor_projects", ["user_id"], unique=False)
    op.create_index(op.f("ix_editor_projects_video_id"), "editor_projects", ["video_id"], unique=False)
    op.create_index(op.f("ix_editor_projects_clip_id"), "editor_projects", ["clip_id"], unique=False)
    op.create_index(op.f("ix_editor_projects_status"), "editor_projects", ["status"], unique=False)

    op.create_table(
        "editor_renders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("export_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", editor_render_status, nullable=False, server_default="queued"),
        sa.Column("preset", editor_render_preset, nullable=False, server_default="tiktok"),
        sa.Column("output_storage_key", sa.Text(), nullable=True),
        sa.Column("output_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("ffmpeg_command_debug", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["project_id"], ["editor_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["export_id"], ["exports.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_editor_renders_project_id"), "editor_renders", ["project_id"], unique=False)
    op.create_index(op.f("ix_editor_renders_user_id"), "editor_renders", ["user_id"], unique=False)
    op.create_index(op.f("ix_editor_renders_export_id"), "editor_renders", ["export_id"], unique=False)
    op.create_index(op.f("ix_editor_renders_status"), "editor_renders", ["status"], unique=False)

    op.add_column("editor_projects", sa.Column("last_render_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f("ix_editor_projects_last_render_id"), "editor_projects", ["last_render_id"], unique=False)
    op.create_foreign_key(
        "fk_editor_projects_last_render_id_editor_renders",
        "editor_projects",
        "editor_renders",
        ["last_render_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "editor_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_type", editor_asset_type, nullable=False, server_default="image"),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.String(length=500), nullable=True),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["project_id"], ["editor_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_editor_assets_project_id"), "editor_assets", ["project_id"], unique=False)
    op.create_index(op.f("ix_editor_assets_user_id"), "editor_assets", ["user_id"], unique=False)

    op.create_table(
        "user_storage_usage",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quota_bytes", sa.BigInteger(), nullable=False),
        sa.Column("used_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("raw_video_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("editor_asset_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("render_output_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_storage_usage")

    op.drop_index(op.f("ix_editor_assets_user_id"), table_name="editor_assets")
    op.drop_index(op.f("ix_editor_assets_project_id"), table_name="editor_assets")
    op.drop_table("editor_assets")

    op.drop_constraint("fk_editor_projects_last_render_id_editor_renders", "editor_projects", type_="foreignkey")
    op.drop_index(op.f("ix_editor_projects_last_render_id"), table_name="editor_projects")
    op.drop_column("editor_projects", "last_render_id")

    op.drop_index(op.f("ix_editor_renders_status"), table_name="editor_renders")
    op.drop_index(op.f("ix_editor_renders_export_id"), table_name="editor_renders")
    op.drop_index(op.f("ix_editor_renders_user_id"), table_name="editor_renders")
    op.drop_index(op.f("ix_editor_renders_project_id"), table_name="editor_renders")
    op.drop_table("editor_renders")

    op.drop_index(op.f("ix_editor_projects_status"), table_name="editor_projects")
    op.drop_index(op.f("ix_editor_projects_clip_id"), table_name="editor_projects")
    op.drop_index(op.f("ix_editor_projects_video_id"), table_name="editor_projects")
    op.drop_index(op.f("ix_editor_projects_user_id"), table_name="editor_projects")
    op.drop_table("editor_projects")

    bind = op.get_bind()
    sa.Enum(name="editor_render_preset").drop(bind, checkfirst=True)
    sa.Enum(name="editor_render_status").drop(bind, checkfirst=True)
    sa.Enum(name="editor_asset_type").drop(bind, checkfirst=True)
    sa.Enum(name="editor_project_status").drop(bind, checkfirst=True)
