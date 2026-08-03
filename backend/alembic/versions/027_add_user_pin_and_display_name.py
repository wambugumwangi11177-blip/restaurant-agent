"""add users.pin_hash/display_name/pin lockout for POS quick-switch (tech-debt D16)

Revision ID: 027_add_user_pin_and_display_name
Revises: 026_add_order_idempotency_key
Create Date: 2026-08-02 00:00:00.000000

Adds users.pin_hash (nullable — opt-in via POST /auth/pin/set),
users.display_name (nullable — no name field existed on User at all before
this), users.pin_failed_attempts / users.pin_locked_until (a lockout counter
deliberately separate from the password-login one, since PIN attempts happen
many times per shift on a shared device).

ATTRIBUTION ONLY: this PIN never gates authorization, only which staff member
a subsequent order is attributed to — see models.py's comment on these
columns and docs/security/threat-model.md.

Idempotent via inspector column checks, matching 020/025's pattern.
"""

from alembic import op
import sqlalchemy as sa

revision = "027_add_user_pin_and_display_name"
down_revision = "026_add_order_idempotency_key"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in sa.inspect(op.get_bind()).get_columns(table_name))


def upgrade():
    if not _column_exists("users", "pin_hash"):
        op.add_column("users", sa.Column("pin_hash", sa.String(), nullable=True))
    if not _column_exists("users", "display_name"):
        op.add_column("users", sa.Column("display_name", sa.String(), nullable=True))
    if not _column_exists("users", "pin_failed_attempts"):
        op.add_column("users", sa.Column("pin_failed_attempts", sa.Integer(), nullable=False, server_default="0"))
    if not _column_exists("users", "pin_locked_until"):
        op.add_column("users", sa.Column("pin_locked_until", sa.DateTime(), nullable=True))


def downgrade():
    if _column_exists("users", "pin_locked_until"):
        op.drop_column("users", "pin_locked_until")
    if _column_exists("users", "pin_failed_attempts"):
        op.drop_column("users", "pin_failed_attempts")
    if _column_exists("users", "display_name"):
        op.drop_column("users", "display_name")
    if _column_exists("users", "pin_hash"):
        op.drop_column("users", "pin_hash")
