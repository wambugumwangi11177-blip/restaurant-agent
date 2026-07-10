"""add token_version to users for JWT session revocation

Revision ID: 017_add_user_token_version
Revises: 016_add_integrity_constraints
Create Date: 2026-07-10 00:00:00.000000

Run with: alembic upgrade head

Adds users.token_version (default 0). A JWT embeds the value it was minted with
as its "ver" claim; get_current_user rejects a token whose ver != the user's
current token_version. Bumping the column (POST /api/v1/auth/logout-all)
invalidates every outstanding session for that user.

`server_default="0"` backfills existing rows so the NOT NULL column applies
cleanly to a populated table. Idempotent via an inspector column check, so it
coexists with a create_all()-seeded schema and re-runs safely on any dialect.
"""

from alembic import op
import sqlalchemy as sa

revision = "017_add_user_token_version"
down_revision = "016_add_integrity_constraints"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in sa.inspect(op.get_bind()).get_columns(table_name))


def upgrade():
    if not _column_exists("users", "token_version"):
        op.add_column(
            "users",
            sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade():
    if _column_exists("users", "token_version"):
        op.drop_column("users", "token_version")
