"""add caption preset to users

Revision ID: 0032
Revises: 0031
Create Date: 2026-07-25 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op


revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("caption_preset", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "caption_preset")
