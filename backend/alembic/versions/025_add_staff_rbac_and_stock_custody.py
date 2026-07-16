"""add staff_role/is_active to users, phone to staff_members, performed_by to
stock_movements, and the stock_transfers table (directives 015 + 016)

Revision ID: 025_add_staff_rbac_and_stock_custody
Revises: 024_add_enterprise_hierarchy
Create Date: 2026-07-15 00:00:00.000000

Run with: alembic upgrade head

Bundles two directives landing in the same change:

  015 (staff RBAC): users.staff_role (nullable — existing STAFF users get NO
  default tier, see the directive's Edge Cases for why guessing one would be
  a real security mistake) + users.is_active (defaults true; lets staff
  deactivation actually revoke a login instead of only hiding a nav link).

  016 (stock custody): stock_movements.performed_by_user_id (nullable —
  historical rows have no actor and can't be backfilled honestly),
  staff_members.phone (nullable — for Twilio-based transfer confirmations),
  and the new stock_transfers table (store->kitchen two-party custody).

Idempotent via inspector checks, so it coexists with a create_all()-seeded
schema (tests, fresh dev DBs) and re-runs safely on any dialect.
"""

from alembic import op
import sqlalchemy as sa

revision = "025_add_staff_rbac_and_stock_custody"
down_revision = "024_add_enterprise_hierarchy"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _insp().get_table_names()


def _column_exists(table: str, column: str) -> bool:
    if not _table_exists(table):
        return False
    return column in [c["name"] for c in _insp().get_columns(table)]


STAFF_ROLE_VALUES = ("OWNER", "MANAGER", "SUPERVISOR", "CONTROLLER", "STOCKKEEPER", "KITCHEN", "WAITER")
TRANSFER_STATUS_VALUES = ("PENDING", "CONFIRMED", "DISPUTED")


def upgrade():
    staff_role_enum = sa.Enum(*STAFF_ROLE_VALUES, name="staffrole")
    staff_role_enum.create(op.get_bind(), checkfirst=True)

    if not _column_exists("users", "staff_role"):
        op.add_column("users", sa.Column("staff_role", staff_role_enum, nullable=True))
    if not _column_exists("users", "is_active"):
        op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))

    if not _column_exists("staff_members", "phone"):
        op.add_column("staff_members", sa.Column("phone", sa.String(), nullable=True))

    if not _column_exists("stock_movements", "performed_by_user_id"):
        op.add_column("stock_movements", sa.Column("performed_by_user_id", sa.Integer(),
                                                     sa.ForeignKey("users.id"), nullable=True))

    if not _table_exists("stock_transfers"):
        # BUG FIX (found running this migration live against real Postgres —
        # the SQLite-only test suite never exercises this path, since SQLite
        # has no named CREATE TYPE at all): op.create_table's automatic
        # enum-creation-on-table-create does NOT respect checkfirst in this
        # SQLAlchemy version — it unconditionally issues CREATE TYPE for any
        # Enum-typed column, ignoring whether the type already exists. That
        # collided with the explicit `.create(checkfirst=True)` call this
        # block used to make first (DuplicateObject, since op.create_table's
        # own unconditional attempt ran right after and found it already
        # there). Fix: drop the explicit pre-creation and let op.create_table
        # be the SOLE creator — but first clear any orphaned type left behind
        # by an earlier partial/interrupted run of this exact migration
        # (confirmed live: alembic_version was still at 024, yet this type
        # already existed) — since the table is confirmed absent right here,
        # any existing type by this name is definitionally orphaned garbage.
        bind = op.get_bind()
        if bind.dialect.name == "postgresql":
            op.execute("DROP TYPE IF EXISTS stocktransferstatus")

        transfer_status_enum = sa.Enum(*TRANSFER_STATUS_VALUES, name="stocktransferstatus")
        op.create_table(
            "stock_transfers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("inventory_item_id", sa.Integer(), sa.ForeignKey("inventory_items.id"), nullable=False),
            sa.Column("quantity", sa.Float(), nullable=False),
            sa.Column("unit", sa.String(), server_default=""),
            sa.Column("from_location", sa.String(), server_default="store"),
            sa.Column("to_location", sa.String(), server_default="kitchen"),
            sa.Column("status", transfer_status_enum, server_default="PENDING"),
            sa.Column("initiated_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("initiated_at", sa.DateTime(), nullable=True),
            sa.Column("confirmed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(), nullable=True),
            sa.Column("confirmed_quantity", sa.Float(), nullable=True),
            sa.Column("notes", sa.Text(), server_default=""),
        )
        op.create_index("ix_stock_transfers_restaurant_status", "stock_transfers",
                         ["restaurant_id", "status"])

    # Backfill: existing ADMIN users are the Owner tier by definition (015).
    # Existing STAFF users are deliberately left NULL — see docstring above.
    op.execute(
        "UPDATE users SET staff_role = 'OWNER' WHERE role = 'ADMIN' AND staff_role IS NULL"
    )


def downgrade():
    if _table_exists("stock_transfers"):
        op.drop_table("stock_transfers")
        sa.Enum(name="stocktransferstatus").drop(op.get_bind(), checkfirst=True)

    if _column_exists("stock_movements", "performed_by_user_id"):
        op.drop_column("stock_movements", "performed_by_user_id")

    if _column_exists("staff_members", "phone"):
        op.drop_column("staff_members", "phone")

    if _column_exists("users", "is_active"):
        op.drop_column("users", "is_active")
    if _column_exists("users", "staff_role"):
        op.drop_column("users", "staff_role")
    sa.Enum(name="staffrole").drop(op.get_bind(), checkfirst=True)
