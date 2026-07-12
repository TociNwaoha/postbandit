"""add facebook video source type

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-22 00:00:00.000000
"""

from alembic import op


revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_enum
                WHERE enumtypid = 'video_source_type'::regtype
                  AND enumlabel = 'facebook'
            ) THEN
                ALTER TYPE video_source_type ADD VALUE 'facebook';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # PostgreSQL enum values are intentionally left in place on downgrade.
    pass
