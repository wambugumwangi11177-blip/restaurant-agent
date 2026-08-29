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

_FK_NAME = "fk_users_active_restaurant_id_restaurants"


def _insp():
    return sa.inspect(op.get_bind())


def _column_exists(table_name: str, column_name: str) -> bool:
    try:
        return any(c["name"] == column_name for c in _insp().get_columns(table_name))
    except sa.exc.NoSuchTableError:
        return False


def _fk_exists(table_name: str, fk_name: str) -> bool:
    try:
        return any(
            fk["name"] == fk_name
            for fk in _insp().get_foreign_keys(table_name)
        )
    except sa.exc.NoSuchTableError:
        return False


def upgrade():
    if not _column_exists("users", "active_restaurant_id"):
        op.add_column(
            "users",
            sa.Column("active_restaurant_id", sa.Integer(), nullable=True),
        )
    if not _fk_exists("users", _FK_NAME):
        op.create_foreign_key(
            _FK_NAME,
            "users",
            "restaurants",
            ["active_restaurant_id"],
            ["id"],
        )


def downgrade():
    if _fk_exists("users", _FK_NAME):
        op.drop_constraint(_FK_NAME, "users", type_="foreignkey")
    if _column_exists("users", "active_restaurant_id"):
        op.drop_column("users", "active_restaurant_id")