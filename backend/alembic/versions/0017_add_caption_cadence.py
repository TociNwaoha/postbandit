"""add no-caption format and caption cadence

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE caption_format ADD VALUE IF NOT EXISTS 'none'")

    caption_cadence = postgresql.ENUM(
        "phrase",
        "split_line",
        "word_by_word",
        "subtitle_block",
        name="caption_cadence",
    )
    caption_cadence.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "exports",
        sa.Column(
            "caption_cadence",
            postgresql.ENUM(name="caption_cadence", create_type=False),
            nullable=False,
            server_default="phrase",
        ),
    )
    op.alter_column("exports", "caption_cadence", server_default="split_line")


def downgrade() -> None:
    op.drop_column("exports", "caption_cadence")
    postgresql.ENUM(name="caption_cadence").drop(op.get_bind(), checkfirst=True)
    # The caption_format enum value is intentionally retained for safe downgrade.
