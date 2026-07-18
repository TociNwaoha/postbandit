"""export reframing fields

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exports", sa.Column("frame_anchor_x", sa.Float(), nullable=True))
    op.add_column("exports", sa.Column("frame_anchor_y", sa.Float(), nullable=True))
    op.add_column("exports", sa.Column("frame_zoom", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("exports", "frame_zoom")
    op.drop_column("exports", "frame_anchor_y")
    op.drop_column("exports", "frame_anchor_x")
