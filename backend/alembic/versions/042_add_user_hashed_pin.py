"""user hashed_pin (audit remediation, Tier 5 item 12 — shared-device quick-switch)

Revision ID: 042_add_user_hashed_pin
Revises: 041_add_user_active_restaurant
Create Date: 2026-07-25 00:00:00.000000

Run with: alembic upgrade head

No PIN/quick-switch mechanism existed at all — every staff account required a
full email+password re-auth, friction on a shared POS/KDS tablet passed
between waiters mid-shift. This column is the missing self-service opt-in:
NULL until a user sets one via POST /auth/pin/set, at which point they appear
in GET /auth/quick-switch/roster for teammates at the same restaurant. See
models.py's User.hashed_pin docstring for why this lives on User rather than
StaffMember.

Idempotent via inspector checks, coexists with a create_all()-seeded schema.
"""

from alembic import op
import sqlalchemy as sa

revision = "042_add_user_hashed_pin"
down_revision = "041_add_user_active_restaurant"
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
    if not _column_exists("users", "hashed_pin"):
        op.add_column("users", sa.Column("hashed_pin", sa.String(), nullable=True))


def downgrade():
    if _column_exists("users", "hashed_pin"):
        op.drop_column("users", "hashed_pin")
