"""add token_usage table

Revision ID: 005_add_token_usage_table
Revises: 004_add_customer_consents
Create Date: 2026-07-07 00:00:00.000000

Run with: alembic upgrade head

Dedicated per-tenant LLM token metering (see models.py TokenUsage docstring) —
replaces the previous approach of writing sentinel rows into agent_messages.
The now-unused agent_messages token columns (llm_model/input_tokens/
output_tokens, migration 002) are left in place: they're nullable and dropping
them adds migration risk for no functional gain. Idempotent via inspector
checks — see 001_add_agent_tables.py's docstring.
"""

from alembic import op
import sqlalchemy as sa

revision = "005_add_token_usage_table"
down_revision = "004_add_customer_consents"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(idx["name"] == index_name for idx in sa.inspect(op.get_bind()).get_indexes(table_name))


def upgrade() -> None:
    if not _table_exists("token_usage"):
        op.create_table(
            "token_usage",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("llm_model", sa.String(), nullable=True),
            sa.Column("input_tokens", sa.Integer(), nullable=True),
            sa.Column("output_tokens", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("token_usage", "ix_token_usage_id"):
        op.create_index("ix_token_usage_id", "token_usage", ["id"])
    if not _index_exists("token_usage", "ix_token_usage_restaurant_created"):
        op.create_index("ix_token_usage_restaurant_created", "token_usage", ["restaurant_id", "created_at"])


def downgrade() -> None:
    op.drop_table("token_usage")
