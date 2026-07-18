"""clip editor aspect and caption position

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE aspect_ratio ADD VALUE IF NOT EXISTS '16:9'")
    op.execute("ALTER TYPE aspect_ratio ADD VALUE IF NOT EXISTS 'original'")
    op.add_column("exports", sa.Column("caption_vertical_position", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("exports", "caption_vertical_position")
    # PostgreSQL enum value removals are intentionally not attempted in downgrade.
