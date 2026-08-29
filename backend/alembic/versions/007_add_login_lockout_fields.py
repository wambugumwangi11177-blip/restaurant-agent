"""add failed_login_attempts and locked_until to users

Revision ID: 007_add_login_lockout_fields
Revises: 006_add_restaurant_owner_phone
Create Date: 2026-07-07 00:00:00.000000

Run with: alembic upgrade head

Security hardening pass (2026-07-07): the login endpoint had zero brute-force
protection — no failed-attempt tracking, no lockout, no rate limiting applied
anywhere despite slowapi being configured. This migration adds the lockout
columns; see routers/auth.py for the enforcement logic. Idempotent via
inspector checks — see 001_add_agent_tables.py's docstring for why.
"""

from alembic import op
import sqlalchemy as sa

revision = "007_add_login_lockout_fields"
down_revision = "006_add_restaurant_owner_phone"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in sa.inspect(op.get_bind()).get_columns(table_name))


def upgrade() -> None:
    if not _column_exists("users", "failed_login_attempts"):
        op.add_column("users", sa.Column("failed_login_attempts", sa.Integer(), nullable=True, server_default="0"))
    if not _column_exists("users", "locked_until"):
        op.add_column("users", sa.Column("locked_until", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        if _column_exists("users", "locked_until"):
            batch_op.drop_column("locked_until")
        if _column_exists("users", "failed_login_attempts"):
            batch_op.drop_column("failed_login_attempts")