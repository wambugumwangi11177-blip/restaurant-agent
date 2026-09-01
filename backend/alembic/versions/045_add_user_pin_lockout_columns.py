"""user pin_failed_attempts / pin_locked_until (quick-switch lockout split)

Revision ID: 045_add_user_pin_lockout_columns
Revises: 044_fix_orderauditaction_enum_labels
Create Date: 2026-08-23 00:00:00.000000

Run with: alembic upgrade head

Quick-switch PIN failures previously incremented failed_login_attempts on the
TARGET user, which /login honors — so any authenticated teammate could submit
5 wrong PINs for a colleague (or the Owner) every 15 minutes and keep them
locked out of password login entirely: a trivial griefing/DoS vector. PIN
attempts now track their own counters, and password login no longer sees them.

Idempotent via inspector checks, coexists with a create_all()-seeded schema.
"""

from alembic import op
import sqlalchemy as sa

revision = "045_add_user_pin_lockout_columns"
down_revision = "044_fix_orderauditaction_enum_labels"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _column_exists(table_name: str, column_name: str) -> bool:
    try:
        return any(c["name"] == column_name for c in _insp().get_columns(table_name))
    except sa.exc.NoSuchTableError:
        return False


def upgrade():
    if not _column_exists("users", "pin_failed_attempts"):
        op.add_column("users", sa.Column("pin_failed_attempts", sa.Integer(), nullable=False, server_default="0"))
    if not _column_exists("users", "pin_locked_until"):
        op.add_column("users", sa.Column("pin_locked_until", sa.DateTime(), nullable=True))


def downgrade():
    if _column_exists("users", "pin_locked_until"):
        op.drop_column("users", "pin_locked_until")
    if _column_exists("users", "pin_failed_attempts"):
        op.drop_column("users", "pin_failed_attempts")
