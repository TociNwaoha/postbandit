"""add beta welcome and limit snapshots

Revision ID: 0037
Revises: 0036
Create Date: 2026-08-16 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op


revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

_CREATOR_QUOTA_BYTES = 5 * 1024 * 1024 * 1024
_CREATOR_HARD_STOP_BYTES = 6 * 1024 * 1024 * 1024


def upgrade() -> None:
    op.add_column("users", sa.Column("beta_welcome_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("beta_storage_quota_bytes", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("beta_storage_hard_stop_bytes", sa.BigInteger(), nullable=True))
    op.add_column("user_storage_usage", sa.Column("hard_stop_bytes", sa.BigInteger(), nullable=False, server_default="0"))

    op.execute(
        "UPDATE users "
        f"SET platforms_allowed = 5, beta_storage_quota_bytes = {_CREATOR_QUOTA_BYTES}, "
        f"beta_storage_hard_stop_bytes = {_CREATOR_HARD_STOP_BYTES} "
        "WHERE is_beta_tester = true AND subscription_status = 'beta_active'"
    )
    op.execute("UPDATE user_storage_usage SET hard_stop_bytes = FLOOR(quota_bytes * 1.2)::BIGINT")
    op.alter_column("user_storage_usage", "hard_stop_bytes", server_default=None)


def downgrade() -> None:
    op.drop_column("user_storage_usage", "hard_stop_bytes")
    op.drop_column("users", "beta_storage_hard_stop_bytes")
    op.drop_column("users", "beta_storage_quota_bytes")
    op.drop_column("users", "beta_welcome_seen_at")
