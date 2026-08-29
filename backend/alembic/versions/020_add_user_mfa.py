"""add TOTP MFA columns to users (Phase 5)

Revision ID: 020_add_user_mfa
Revises: 019_add_conversation_turns
Create Date: 2026-07-12 00:00:00.000000

Run with: alembic upgrade head

Adds users.mfa_secret (base32 TOTP secret, nullable) and users.mfa_enabled
(bool, default false). Existing users are unaffected — MFA is opt-in per user via
the /mfa/setup + /mfa/enable flow, and only enforced at login once mfa_enabled
is true.

Idempotent via inspector column checks, so it coexists with a create_all()-seeded
schema (tests) and re-runs safely on any dialect.
"""

from alembic import op
import sqlalchemy as sa

revision = "020_add_user_mfa"
down_revision = "019_add_conversation_turns"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_context().connection
    return any(c["name"] == column_name for c in sa.inspect(conn).get_columns(table_name))


def upgrade():
    if not _column_exists("users", "mfa_secret"):
        op.add_column("users", sa.Column("mfa_secret", sa.String(), nullable=True))
    if not _column_exists("users", "mfa_enabled"):
        op.add_column("users", sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    if _column_exists("users", "mfa_enabled"):
        op.drop_column("users", "mfa_enabled")
    if _column_exists("users", "mfa_secret"):
        op.drop_column("users", "mfa_secret")