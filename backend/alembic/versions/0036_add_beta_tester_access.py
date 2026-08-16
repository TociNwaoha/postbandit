"""add beta tester access fields

Revision ID: 0036
Revises: 0035
Create Date: 2026-08-16 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op


revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_beta_tester", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("beta_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "beta_expires_at")
    op.drop_column("users", "is_beta_tester")
