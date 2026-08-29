"""add auth_tokens table and users.is_email_verified

Revision ID: 034_add_auth_tokens_and_email_verified
Revises: 033_add_impersonation_sessions
Create Date: 2026-07-17 00:00:00.000000

Run with: alembic upgrade head

Backs password reset + email verification (security audit 2026-07-17: neither
existed at all). auth_tokens is a shared single-use/short-lived token table
for both purposes (see models.AuthToken); only a SHA-256 hash of the token is
stored, never the raw value.

users.is_email_verified defaults False for new signups but is backfilled True
for every existing user — they were already trusted before this column
existed, and nothing gates on the flag today, so retroactively marking them
unverified would just be noise, not a real safety measure.

Idempotent via inspector checks; coexists with create_all() (see 033's
docstring — same reasoning applies here).
"""

from alembic import op
import sqlalchemy as sa

revision = "034_add_auth_tokens_and_email_verified"
down_revision = "033_add_impersonation_sessions"
branch_labels = None
depends_on = None

AUTH_TOKEN_PURPOSE_VALUES = ["password_reset", "email_verify"]


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _insp().get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in _insp().get_columns(table_name))


def upgrade():
    if not _column_exists("users", "is_email_verified"):
        # New signups must default to False so they go through email verification.
        # Existing users are backfilled to True immediately after column creation
        # because they were trusted before this column existed.
        op.add_column(
            "users",
            sa.Column("is_email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.execute("UPDATE users SET is_email_verified = TRUE")

    if not _table_exists("auth_tokens"):
        # op.create_table's automatic enum-creation-on-table-create does not
        # respect checkfirst in this SQLAlchemy version (see 025/032's fix
        # commit) — so don't pre-create the type explicitly; let
        # op.create_table be the sole creator, after clearing any orphaned
        # type a prior partial run might have left behind.
        bind = op.get_bind()
        if bind.dialect.name == "postgresql":
            op.execute("DROP TYPE IF EXISTS authtokenpurpose")

        purpose_enum = sa.Enum(*AUTH_TOKEN_PURPOSE_VALUES, name="authtokenpurpose")
        op.create_table(
            "auth_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("token_hash", sa.String(), nullable=False),
            sa.Column("purpose", purpose_enum, nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_auth_tokens_user_id", "auth_tokens", ["user_id"])
        op.create_index("ix_auth_tokens_token_hash", "auth_tokens", ["token_hash"])


def downgrade():
    if _table_exists("auth_tokens"):
        op.drop_table("auth_tokens")
        if op.get_bind().dialect.name == "postgresql":
            sa.Enum(name="authtokenpurpose").drop(op.get_bind(), checkfirst=True)
    if _column_exists("users", "is_email_verified"):
        op.drop_column("users", "is_email_verified")