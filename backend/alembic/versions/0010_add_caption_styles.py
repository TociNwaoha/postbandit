"""add caption styles

Revision ID: 0010_add_caption_styles
Revises: 0009
Create Date: 2026-04-30 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0010_add_caption_styles"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE caption_style ADD VALUE IF NOT EXISTS 'kinetic_bold'")
    op.execute("ALTER TYPE caption_style ADD VALUE IF NOT EXISTS 'cinema_outline'")
    op.execute("ALTER TYPE caption_style ADD VALUE IF NOT EXISTS 'clean_highlight'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely in-place.
    # Keep downgrade as a no-op to preserve existing data compatibility.
    pass
