"""add durable publish scheduling and history snapshots

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE publish_status ADD VALUE IF NOT EXISTS 'scheduled'")
        op.execute("ALTER TYPE publish_status ADD VALUE IF NOT EXISTS 'cancelled'")

    op.add_column("publish_jobs", sa.Column("timezone", sa.String(length=100), nullable=True))
    op.add_column(
        "publish_jobs",
        sa.Column("destination_display_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "publish_jobs",
        sa.Column("content_title_snapshot", sa.String(length=500), nullable=True),
    )

    op.execute(
        """
        UPDATE publish_jobs AS pj
        SET destination_display_name = COALESCE(
            ca.display_name,
            ca.username_or_channel_name,
            ca.external_account_id
        )
        FROM connected_accounts AS ca
        WHERE pj.connected_account_id = ca.id
          AND pj.destination_display_name IS NULL
        """
    )
    op.execute(
        """
        UPDATE publish_jobs AS pj
        SET content_title_snapshot = COALESCE(c.title, v.title, 'Scheduled post')
        FROM clips AS c
        LEFT JOIN videos AS v ON v.id = c.video_id
        WHERE pj.clip_id = c.id
          AND pj.content_title_snapshot IS NULL
        """
    )

    op.drop_constraint(
        "publish_jobs_connected_account_id_fkey",
        "publish_jobs",
        type_="foreignkey",
    )
    op.drop_constraint("publish_jobs_export_id_fkey", "publish_jobs", type_="foreignkey")
    op.drop_constraint("publish_jobs_clip_id_fkey", "publish_jobs", type_="foreignkey")

    op.alter_column("publish_jobs", "connected_account_id", nullable=True)
    op.alter_column("publish_jobs", "export_id", nullable=True)
    op.alter_column("publish_jobs", "clip_id", nullable=True)

    op.create_foreign_key(
        "fk_publish_jobs_connected_account_history",
        "publish_jobs",
        "connected_accounts",
        ["connected_account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_publish_jobs_export_history",
        "publish_jobs",
        "exports",
        ["export_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_publish_jobs_clip_history",
        "publish_jobs",
        "clips",
        ["clip_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        """
        UPDATE publish_jobs
        SET status = 'scheduled'
        WHERE publish_mode = 'scheduled'
          AND scheduled_for > CURRENT_TIMESTAMP
          AND status = 'queued'
        """
    )
    op.create_index(
        "idx_publish_jobs_due_scheduled",
        "publish_jobs",
        ["scheduled_for"],
        unique=False,
        postgresql_where=sa.text("status = 'scheduled'"),
    )


def downgrade() -> None:
    op.drop_index("idx_publish_jobs_due_scheduled", table_name="publish_jobs")

    op.execute(
        """
        UPDATE publish_jobs
        SET status = 'queued'
        WHERE status IN ('scheduled', 'cancelled')
        """
    )

    op.drop_constraint(
        "fk_publish_jobs_connected_account_history",
        "publish_jobs",
        type_="foreignkey",
    )
    op.drop_constraint("fk_publish_jobs_export_history", "publish_jobs", type_="foreignkey")
    op.drop_constraint("fk_publish_jobs_clip_history", "publish_jobs", type_="foreignkey")

    # Downgrading to the legacy non-null schema cannot retain orphan history rows.
    op.execute(
        """
        DELETE FROM publish_jobs
        WHERE connected_account_id IS NULL
           OR export_id IS NULL
           OR clip_id IS NULL
        """
    )
    op.alter_column("publish_jobs", "connected_account_id", nullable=False)
    op.alter_column("publish_jobs", "export_id", nullable=False)
    op.alter_column("publish_jobs", "clip_id", nullable=False)

    op.create_foreign_key(
        "publish_jobs_connected_account_id_fkey",
        "publish_jobs",
        "connected_accounts",
        ["connected_account_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "publish_jobs_export_id_fkey",
        "publish_jobs",
        "exports",
        ["export_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "publish_jobs_clip_id_fkey",
        "publish_jobs",
        "clips",
        ["clip_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_column("publish_jobs", "content_title_snapshot")
    op.drop_column("publish_jobs", "destination_display_name")
    op.drop_column("publish_jobs", "timezone")
    # PostgreSQL enum values are intentionally retained for safe downgrade.
