"""token usage stats + telegram username

Revision ID: 0003_token_usage
Revises: 0002_unique_indexes
Create Date: 2026-04-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_token_usage"
down_revision = "0002_unique_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("telegram_username", sa.String(length=64), nullable=False, server_default=""),
    )
    op.create_index("ix_users_telegram_username", "users", ["telegram_username"])

    op.create_table(
        "token_usage_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("telegram_user_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("telegram_username", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="rag_search"),
        sa.Column("model", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.create_index("ix_token_usage_events_user_id", "token_usage_events", ["user_id"])
    op.create_index("ix_token_usage_events_telegram_user_id", "token_usage_events", ["telegram_user_id"])
    op.create_index("ix_token_usage_events_telegram_username", "token_usage_events", ["telegram_username"])
    op.create_index("ix_token_usage_events_source", "token_usage_events", ["source"])
    op.create_index("ix_token_usage_events_model", "token_usage_events", ["model"])
    op.create_index("ix_token_usage_events_request_id", "token_usage_events", ["request_id"])

    op.create_table(
        "user_token_usage_day",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False, server_default=sa.text("current_date")),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("user_id", "day", name="uq_user_token_day"),
    )
    op.create_index("ix_user_token_usage_day_user_id", "user_token_usage_day", ["user_id"])
    op.create_index("ix_user_token_usage_day_day", "user_token_usage_day", ["day"])


def downgrade() -> None:
    op.drop_index("ix_user_token_usage_day_day", table_name="user_token_usage_day")
    op.drop_index("ix_user_token_usage_day_user_id", table_name="user_token_usage_day")
    op.drop_table("user_token_usage_day")

    op.drop_index("ix_token_usage_events_request_id", table_name="token_usage_events")
    op.drop_index("ix_token_usage_events_model", table_name="token_usage_events")
    op.drop_index("ix_token_usage_events_source", table_name="token_usage_events")
    op.drop_index("ix_token_usage_events_telegram_username", table_name="token_usage_events")
    op.drop_index("ix_token_usage_events_telegram_user_id", table_name="token_usage_events")
    op.drop_index("ix_token_usage_events_user_id", table_name="token_usage_events")
    op.drop_table("token_usage_events")

    op.drop_index("ix_users_telegram_username", table_name="users")
    op.drop_column("users", "telegram_username")

