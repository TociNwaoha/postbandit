"""add caption style to users

Revision ID: 0034
Revises: 0033
Create Date: 2026-07-26 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op


revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("caption_style", sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "caption_style")
