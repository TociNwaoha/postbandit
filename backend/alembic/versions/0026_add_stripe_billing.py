"""add stripe billing

Revision ID: 0026
Revises: 0025
Create Date: 2026-07-09 00:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("stripe_customer_id", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column("billing_plan", sa.String(length=50), nullable=False, server_default="trial"),
    )
    op.add_column(
        "users",
        sa.Column("subscription_status", sa.String(length=50), nullable=False, server_default="trialing"),
    )
    op.add_column("users", sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("billing_period_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("billing_period_end", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("platforms_allowed", sa.Integer(), nullable=False, server_default="3"),
    )
    op.create_index("ix_users_stripe_customer_id", "users", ["stripe_customer_id"], unique=True)
    op.create_index("ix_users_stripe_subscription_id", "users", ["stripe_subscription_id"], unique=True)

    op.create_table(
        "processed_stripe_events",
        sa.Column("event_id", sa.String(length=255), primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_processed_stripe_events_event_type", "processed_stripe_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_processed_stripe_events_event_type", table_name="processed_stripe_events")
    op.drop_table("processed_stripe_events")

    op.drop_index("ix_users_stripe_subscription_id", table_name="users")
    op.drop_index("ix_users_stripe_customer_id", table_name="users")
    op.drop_column("users", "platforms_allowed")
    op.drop_column("users", "billing_period_end")
    op.drop_column("users", "billing_period_start")
    op.drop_column("users", "trial_ends_at")
    op.drop_column("users", "subscription_status")
    op.drop_column("users", "billing_plan")
    op.drop_column("users", "stripe_subscription_id")
    op.drop_column("users", "stripe_customer_id")
