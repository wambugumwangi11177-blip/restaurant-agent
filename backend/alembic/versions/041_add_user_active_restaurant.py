"""user active_restaurant_id (audit remediation, Tier 5 item 11 — multi-restaurant switcher)

Revision ID: 041_add_user_active_restaurant
Revises: 040_add_notification_outbox
Create Date: 2026-07-25 00:00:00.000000

Run with: alembic upgrade head

Every router resolved "the" restaurant for a tenant via
routers/deps.py::get_or_create_restaurant, which always took the tenant's
FIRST restaurant — fine for the overwhelming single-restaurant case, a real
gap for a chain (Organization/Region already existed from Phase 10, just
never wired into restaurant selection). This column records which restaurant
a user is currently viewing; NULL preserves today's exact "first restaurant"
behavior. See models.py's User.active_restaurant_id docstring and
routers/restaurants.py.

Idempotent via inspector checks, coexists with a create_all()-seeded schema.
"""

from alembic import op
import sqlalchemy as sa

revision = "041_add_user_active_restaurant"
down_revision = "040_add_notification_outbox"
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
    if not _column_exists("users", "active_restaurant_id"):
        op.add_column(
            "users",
            sa.Column("active_restaurant_id", sa.Integer(),
                      sa.ForeignKey("restaurants.id"), nullable=True),
        )


def downgrade():
    if _column_exists("users", "active_restaurant_id"):
        op.drop_column("users", "active_restaurant_id")
