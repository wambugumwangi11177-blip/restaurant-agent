"""add token usage columns to agent_messages

Revision ID: 002_add_agent_message_token_usage
Revises: 001_add_agent_tables
Create Date: 2026-07-07 00:00:00.000000

Run with: alembic upgrade head

Per-tenant token metering for the Phase 2 LLM orchestrator (directives/012_agentic_roadmap.md).
Tracked from the first live LLM call, before any billing model exists, so usage data is
available when pricing tiers are designed.

Idempotent via inspector column checks (see 001_add_agent_tables.py's docstring for why
raw "ADD COLUMN IF NOT EXISTS" isn't used — it's Postgres-only syntax, and this project's
local dev/tests run on SQLite).
"""

from alembic import op
import sqlalchemy as sa

revision = "002_add_agent_message_token_usage"
down_revision = "001_add_agent_tables"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in sa.inspect(op.get_bind()).get_columns(table_name))


def upgrade() -> None:
    if not _column_exists("agent_messages", "llm_model"):
        op.add_column("agent_messages", sa.Column("llm_model", sa.String(), nullable=True))
    if not _column_exists("agent_messages", "input_tokens"):
        op.add_column("agent_messages", sa.Column("input_tokens", sa.Integer(), nullable=True))
    if not _column_exists("agent_messages", "output_tokens"):
        op.add_column("agent_messages", sa.Column("output_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    # batch_alter_table for SQLite compatibility — see 003's downgrade() for why.
    with op.batch_alter_table("agent_messages") as batch_op:
        batch_op.drop_column("output_tokens")
        batch_op.drop_column("input_tokens")
        batch_op.drop_column("llm_model")
