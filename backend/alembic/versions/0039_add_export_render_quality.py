"""add export render quality

Revision ID: 0039
Revises: 0038
Create Date: 2026-08-17 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op


revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "exports",
        sa.Column("render_quality", sa.String(length=10), nullable=False, server_default="720p"),
    )
    op.alter_column("exports", "render_quality", server_default=None)


def downgrade() -> None:
    op.drop_column("exports", "render_quality")
