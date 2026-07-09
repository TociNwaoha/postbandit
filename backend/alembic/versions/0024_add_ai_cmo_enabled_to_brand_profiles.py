"""add ai cmo enabled flag to brand profiles

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-08 22:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "brand_profiles",
        sa.Column("ai_cmo_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.alter_column("brand_profiles", "ai_cmo_enabled", server_default=None)


def downgrade() -> None:
    op.drop_column("brand_profiles", "ai_cmo_enabled")
