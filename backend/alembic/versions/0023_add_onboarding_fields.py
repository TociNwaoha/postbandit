"""add onboarding fields

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("onboarding_skipped_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("onboarding_role", sa.String(length=50), nullable=True))
    op.add_column(
        "users",
        sa.Column("onboarding_metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # Existing users should not be interrupted by the new onboarding gate.
    op.execute(
        """
        UPDATE users
        SET onboarding_completed_at = COALESCE(created_at, now())
        WHERE onboarding_completed_at IS NULL
          AND onboarding_skipped_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("users", "onboarding_metadata_json")
    op.drop_column("users", "onboarding_role")
    op.drop_column("users", "onboarding_skipped_at")
    op.drop_column("users", "onboarding_completed_at")
