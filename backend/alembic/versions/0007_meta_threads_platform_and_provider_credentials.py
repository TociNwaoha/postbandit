"""meta threads platform enum extension

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-12 00:00:00.000000
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE social_platform ADD VALUE IF NOT EXISTS 'threads'")


def downgrade() -> None:
    # PostgreSQL enums do not support safe value removal in-place.
    # Keep downgrade as no-op to avoid destructive enum recreation.
    pass

