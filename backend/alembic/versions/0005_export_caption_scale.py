"""export caption scale

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exports", sa.Column("caption_scale", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("exports", "caption_scale")

