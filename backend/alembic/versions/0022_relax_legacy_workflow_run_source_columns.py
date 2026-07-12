"""relax legacy workflow run source columns

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-23 00:00:00.000000
"""

from alembic import op


revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Some deployed databases briefly had source snapshot fields directly on
    # social_workflow_runs. Current code stores source data on
    # social_workflow_source_posts, so these legacy columns must not block run
    # creation when they exist.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'social_workflow_runs'
                  AND column_name = 'source_platform'
            ) THEN
                ALTER TABLE social_workflow_runs ALTER COLUMN source_platform DROP NOT NULL;
            END IF;

            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'social_workflow_runs'
                  AND column_name = 'source_external_post_id'
            ) THEN
                ALTER TABLE social_workflow_runs ALTER COLUMN source_external_post_id DROP NOT NULL;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # This repair intentionally does not restore NOT NULL constraints because
    # current application code no longer populates these legacy columns.
    pass
