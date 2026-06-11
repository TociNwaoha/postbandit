"""add clip overlay assets and export overlay snapshots

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clip_overlay_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("clip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.String(length=500), nullable=True),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["clip_id"], ["clips.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_clip_overlay_assets_clip_id"), "clip_overlay_assets", ["clip_id"], unique=False)
    op.create_index(op.f("ix_clip_overlay_assets_user_id"), "clip_overlay_assets", ["user_id"], unique=False)

    op.add_column("exports", sa.Column("overlay_image_asset_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("exports", sa.Column("overlay_image_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("exports", sa.Column("overlay_text_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index(op.f("ix_exports_overlay_image_asset_id"), "exports", ["overlay_image_asset_id"], unique=False)
    op.create_foreign_key(
        "fk_exports_overlay_image_asset_id_clip_overlay_assets",
        "exports",
        "clip_overlay_assets",
        ["overlay_image_asset_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_exports_overlay_image_asset_id_clip_overlay_assets",
        "exports",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_exports_overlay_image_asset_id"), table_name="exports")
    op.drop_column("exports", "overlay_text_config")
    op.drop_column("exports", "overlay_image_config")
    op.drop_column("exports", "overlay_image_asset_id")

    op.drop_index(op.f("ix_clip_overlay_assets_user_id"), table_name="clip_overlay_assets")
    op.drop_index(op.f("ix_clip_overlay_assets_clip_id"), table_name="clip_overlay_assets")
    op.drop_table("clip_overlay_assets")
