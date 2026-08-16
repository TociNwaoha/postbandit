"""rename elite billing plan to agency

Revision ID: 0038
Revises: 0037
Create Date: 2026-08-16 00:00:00.000000
"""

from alembic import op


revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE users SET billing_plan = 'agency' WHERE billing_plan = 'elite'")
    op.execute(
        "UPDATE users SET onboarding_metadata_json = jsonb_set(onboarding_metadata_json, '{selected_plan}', '\"agency\"'::jsonb) "
        "WHERE onboarding_metadata_json ->> 'selected_plan' = 'elite'"
    )


def downgrade() -> None:
    op.execute("UPDATE users SET billing_plan = 'elite' WHERE billing_plan = 'agency'")
    op.execute(
        "UPDATE users SET onboarding_metadata_json = jsonb_set(onboarding_metadata_json, '{selected_plan}', '\"elite\"'::jsonb) "
        "WHERE onboarding_metadata_json ->> 'selected_plan' = 'agency'"
    )
