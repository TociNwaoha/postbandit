"""add connected account token state

Revision ID: 0027
Revises: 0026
Create Date: 2026-07-10 22:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "connected_accounts",
        sa.Column("token_expired", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "connected_accounts",
        sa.Column("last_token_refresh", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("connected_accounts", "token_expired", server_default=None)


def downgrade() -> None:
    op.drop_column("connected_accounts", "last_token_refresh")
    op.drop_column("connected_accounts", "token_expired")
