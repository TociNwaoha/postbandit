"""add is full video to clips

Revision ID: 0033
Revises: 0032
Create Date: 2026-07-25 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op


revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clips",
        sa.Column("is_full_video", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("clips", "is_full_video", server_default=None)


def downgrade() -> None:
    op.drop_column("clips", "is_full_video")
