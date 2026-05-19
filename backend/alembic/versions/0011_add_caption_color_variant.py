"""add caption color variant

Revision ID: 0011_add_caption_color_variant
Revises: 0010_add_caption_styles
Create Date: 2026-04-30 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0011_add_caption_color_variant"
down_revision: Union[str, None] = "0010_add_caption_styles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_type
                WHERE typname = 'caption_color_variant'
            ) THEN
                CREATE TYPE caption_color_variant AS ENUM ('classic', 'warm', 'cool');
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        ALTER TABLE exports
        ADD COLUMN IF NOT EXISTS caption_color_variant caption_color_variant
        """
    )


def downgrade() -> None:
    # PostgreSQL enum values/types cannot be removed safely in-place where data may exist.
    # Keep downgrade non-destructive for production safety.
    pass
