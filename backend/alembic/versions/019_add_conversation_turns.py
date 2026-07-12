"""add conversation_turns for WhatsApp short-term memory (Phase 6)

Revision ID: 019_add_conversation_turns
Revises: 018_add_token_usage_prompt_version
Create Date: 2026-07-12 00:00:00.000000

Run with: alembic upgrade head

Creates the conversation_turns table backing the WhatsApp orchestrator's
short-term memory (ai/whatsapp/conversation.py). Nothing writes to it until
FEATURE_CONVERSATION_MEMORY is enabled, so this migration is safe to deploy
ahead of the feature.

Idempotent via an inspector table check, so it coexists with a create_all()-seeded
schema (tests) and re-runs safely on any dialect (SQLite/Postgres).
"""

from alembic import op
import sqlalchemy as sa

revision = "019_add_conversation_turns"
down_revision = "018_add_token_usage_prompt_version"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if _table_exists("conversation_turns"):
        return
    op.create_table(
        "conversation_turns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_conversation_turns_restaurant_created",
        "conversation_turns",
        ["restaurant_id", "created_at"],
    )


def downgrade():
    if _table_exists("conversation_turns"):
        op.drop_index("ix_conversation_turns_restaurant_created", table_name="conversation_turns")
        op.drop_table("conversation_turns")
