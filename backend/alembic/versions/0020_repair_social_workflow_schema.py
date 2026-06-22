"""repair social workflow schema drift

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-22 00:00:00.000000
"""

from alembic import op


revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Production briefly had an older 0018 revision applied before the workflow
    # model settled. Keep this repair idempotent so fresh DBs and deployed DBs
    # both converge on the same model-compatible schema.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'social_workflow_status') THEN
                CREATE TYPE social_workflow_status AS ENUM ('active', 'paused');
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'social_workflow_copy_mode') THEN
                CREATE TYPE social_workflow_copy_mode AS ENUM ('reuse_source', 'platform_ai', 'both');
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'social_workflow_run_status') THEN
                CREATE TYPE social_workflow_run_status AS ENUM (
                    'detected',
                    'importing',
                    'imported_processing',
                    'ready_to_publish',
                    'publishing',
                    'completed',
                    'original_required',
                    'import_failed',
                    'partial_failed'
                );
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'social_workflows' AND column_name = 'status'
            ) THEN
                ALTER TABLE social_workflows ADD COLUMN status social_workflow_status;
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'social_workflows' AND column_name = 'enabled'
                ) THEN
                    UPDATE social_workflows
                    SET status = CASE WHEN enabled IS FALSE THEN 'paused' ELSE 'active' END::social_workflow_status;
                ELSE
                    UPDATE social_workflows SET status = 'active'::social_workflow_status;
                END IF;
                ALTER TABLE social_workflows ALTER COLUMN status SET DEFAULT 'active'::social_workflow_status;
                ALTER TABLE social_workflows ALTER COLUMN status SET NOT NULL;
            END IF;

            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'social_workflows'
                  AND column_name = 'copy_mode'
                  AND udt_name <> 'social_workflow_copy_mode'
            ) THEN
                ALTER TABLE social_workflows ALTER COLUMN copy_mode DROP DEFAULT;
                ALTER TABLE social_workflows
                ALTER COLUMN copy_mode TYPE social_workflow_copy_mode
                USING (
                    CASE
                        WHEN copy_mode::text IN ('reuse_source', 'platform_ai', 'both') THEN copy_mode::text
                        WHEN copy_mode::text IN ('ai_copy', 'ai', 'platform_copy') THEN 'platform_ai'
                        WHEN copy_mode::text IN ('source', 'source_copy', 'original', 'reuse_original') THEN 'reuse_source'
                        ELSE 'both'
                    END
                )::social_workflow_copy_mode;
                ALTER TABLE social_workflows ALTER COLUMN copy_mode SET DEFAULT 'both'::social_workflow_copy_mode;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'social_workflows' AND column_name = 'auto_publish'
            ) THEN
                ALTER TABLE social_workflows ADD COLUMN auto_publish boolean NOT NULL DEFAULT true;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'social_workflows' AND column_name = 'destination_targets_json'
            ) THEN
                ALTER TABLE social_workflows
                ADD COLUMN destination_targets_json jsonb NOT NULL DEFAULT '[]'::jsonb;
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'social_workflows' AND column_name = 'destination_configs'
                ) THEN
                    UPDATE social_workflows SET destination_targets_json = COALESCE(destination_configs, '[]'::jsonb);
                END IF;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'social_workflows' AND column_name = 'poll_cursor_json'
            ) THEN
                ALTER TABLE social_workflows ADD COLUMN poll_cursor_json jsonb NOT NULL DEFAULT '{}'::jsonb;
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'social_workflows' AND column_name = 'cursor_json'
                ) THEN
                    UPDATE social_workflows SET poll_cursor_json = COALESCE(cursor_json, '{}'::jsonb);
                END IF;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'social_workflows' AND column_name = 'last_polled_at'
            ) THEN
                ALTER TABLE social_workflows ADD COLUMN last_polled_at timestamptz;
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'social_workflows' AND column_name = 'last_checked_at'
                ) THEN
                    UPDATE social_workflows SET last_polled_at = last_checked_at;
                END IF;
            END IF;
        END $$;
        """
    )

    op.execute("CREATE INDEX IF NOT EXISTS ix_social_workflows_status ON social_workflows (status)")

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'social_workflow_runs'
                  AND column_name = 'status'
                  AND udt_name <> 'social_workflow_run_status'
            ) THEN
                ALTER TABLE social_workflow_runs ALTER COLUMN status DROP DEFAULT;
                ALTER TABLE social_workflow_runs
                ALTER COLUMN status TYPE social_workflow_run_status
                USING (
                    CASE
                        WHEN status::text IN (
                            'detected',
                            'importing',
                            'imported_processing',
                            'ready_to_publish',
                            'publishing',
                            'completed',
                            'original_required',
                            'import_failed',
                            'partial_failed'
                        ) THEN status::text
                        WHEN status::text IN ('failed', 'error') THEN 'import_failed'
                        ELSE 'detected'
                    END
                )::social_workflow_run_status;
                ALTER TABLE social_workflow_runs ALTER COLUMN status SET DEFAULT 'detected'::social_workflow_run_status;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'social_workflow_runs' AND column_name = 'publish_job_ids_json'
            ) THEN
                ALTER TABLE social_workflow_runs ADD COLUMN publish_job_ids_json jsonb NOT NULL DEFAULT '[]'::jsonb;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'social_workflow_runs' AND column_name = 'destination_results_json'
            ) THEN
                ALTER TABLE social_workflow_runs ADD COLUMN destination_results_json jsonb NOT NULL DEFAULT '{}'::jsonb;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # This is a production repair migration. Downgrading it would need to know
    # which historic 0018 shape each database had, so it is intentionally a no-op.
    pass
