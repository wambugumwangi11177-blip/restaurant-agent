"""add prompt_version to token_usage for AIOps prompt traceability

Revision ID: 018_add_token_usage_prompt_version
Revises: 017_add_user_token_version
Create Date: 2026-07-11 00:00:00.000000

Run with: alembic upgrade head

Adds token_usage.prompt_version (nullable). Every metered narration turn now
records the version of the narration prompt that produced it
(ai/reasoning/narrator.py::PROMPT_VERSION), so a change in token spend or
grounding rate can be traced to a specific prompt revision rather than guessed.

Nullable with no backfill: rows written before this column existed are simply
"unknown" version, which the AIOps summary reports as such. Idempotent via an
inspector column check, so it coexists with a create_all()-seeded schema and
re-runs safely on any dialect.
"""

from alembic import op
import sqlalchemy as sa

revision = "018_add_token_usage_prompt_version"
down_revision = "017_add_user_token_version"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in sa.inspect(op.get_bind()).get_columns(table_name))


def upgrade():
    if not _column_exists("token_usage", "prompt_version"):
        op.add_column(
            "token_usage",
            sa.Column("prompt_version", sa.String(), nullable=True),
        )


def downgrade():
    if _column_exists("token_usage", "prompt_version"):
        op.drop_column("token_usage", "prompt_version")
