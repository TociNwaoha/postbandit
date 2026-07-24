"""add clip content brief

Revision ID: 0031
Revises: 0030
Create Date: 2026-07-24 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clips", sa.Column("content_brief", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("clips", "content_brief")
