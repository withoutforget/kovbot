"""unique indexes for idempotent upserts

Revision ID: 0002_unique_indexes
Revises: 0001_initial
Create Date: 2026-04-16
"""

from __future__ import annotations

from alembic import op

revision = "0002_unique_indexes"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1:1 user profile (used in UPSERT/ensure flow)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_user_profiles_user_id ON user_profiles (user_id)"
    )

    # 1 schedule row per (user, key) (used in UPSERT schedule + ensure defaults)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_user_schedule_user_key ON user_schedule (user_id, schedule_key)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_user_schedule_user_key")
    op.execute("DROP INDEX IF EXISTS ux_user_profiles_user_id")

