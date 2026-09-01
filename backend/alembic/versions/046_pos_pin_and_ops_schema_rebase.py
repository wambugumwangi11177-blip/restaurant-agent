"""schema rebase: add POS offline + PIN columns this branch's models expect

Revision ID: 046_pos_pin_and_ops_schema_rebase
Revises: 045_add_user_pin_lockout_columns
Create Date: 2026-09-01

Run with: alembic upgrade head

WHY THIS EXISTS: the migration lineages forked after ~024
(branch feat/pos-offline-pin-hardening vs deployed feat/staff-rbac-stock-custody-twilio).
The deployed lineage implicitly won: prod (Neon) is stamped at
`045_add_user_pin_lockout_columns`,so this branch adopted that chain (versions/025*-045*)
and now re-introduces, as ONE additive migration, the deltas from the
retired local revisions (025_add_user_is_active .. 030_add_operational_core_tables)
that prod does NOT already have + the renamed PIN column this branch's code uses.

CRITICAL: `users.hashed_pin` (deployed lineage)and `users.pin_hash` (this branch)are THE SAME FEATURE
with REAL staff PINs already stored in `hashed_pin`. We RENAME the column
(not add a second)so existing staff keep their PINs; auth.get_password_hash
is the only hashing scheme on both lineages,. The rename happens FIRST so the
whole migration is data-preserving.



Verified against prod on 2026-09-01 (read-only information_schema):
every op below fires ONLY on columns that are genuinely MISSING in prod.

Idempotent by design, inspector-guarded like all siblings in this dir.

"""

from alembic import op
import sqlalchemy as sa


revision = "046_pos_pin_and_ops_schema_rebase"
down_revision = "045_add_user_pin_lockout_columns"
branch_labels=None
depends_on=None


def _insp():
    return sa.inspect(op.get_bind())


def _column_exists(table_name: str, column_name: str) -> bool:
    try:
        return any(c["name"] == column_name for c in _insp().get_columns(table_name))
    except sa.exc.NoSuchTableError:
        return False


def _fk_exists(table_name: str, column_name: str) -> bool:
    try:
        return any(
            fk["constrained_columns"] == [column_name]
            for fk in _insp().get_foreign_keys(table_name)
        )
    except sa.exc.NoSuchTableError:
        return False


def _unique_exists(table_name: str, constraint_name: str) -> bool:
    try:
        return any(
            uc["name"] == constraint_name
            for uc in _insp().get_unique_constraints(table_name)
        )
    except sa.exc.NoSuchTableError:
        return False


def upgrade() -> None:
    # 1. users: rename hashed_pin→pin_hash (preserves real staff PINs, then add display_name
    if (_column_exists("users", "hashed_pin")and not _column_exists("users", "pin_hash")):
        op.alter_column("users", "hashed_pin", new_column_name="pin_hash")
    if not _column_exists("users", "display_name"):
        op.add_column("users", sa.Column("display_name", sa.String(), nullable=True))

    # 2. orders: the POS discount/tax/refund/void/payments columns this branch's models.py needs
    if not _column_exists("orders", "discount_cents"):
        op.add_column("orders", sa.Column("discount_cents", sa.Integer(), nullable=True))
    if not _column_exists("orders", "discount_reason"):
        op.add_column("orders", sa.Column("discount_reason", sa.String(), nullable=True))
    if not _column_exists("orders", "void_reason"):
        op.add_column("orders", sa.Column("void_reason", sa.String(), nullable=True))
    if not _column_exists("orders", "refund_cents"):
        op.add_column("orders", sa.Column("refund_cents", sa.Integer(), nullable=True))
    if not _column_exists("orders", "refund_reason"):
        op.add_column("orders", sa.Column("refund_reason", sa.String(), nullable=True))
    if not _column_exists("orders", "tax_cents"):
        op.add_column("orders", sa.Column("tax_cents", sa.Integer(), nullable=True))
    if not _column_exists("orders", "service_charge_cents"):
        op.add_column("orders", sa.Column("service_charge_cents", sa.Integer(), nullable=True))
    if not _column_exists("orders", "idempotency_key"):
        op.add_column("orders", sa.Column("idempotency_key", sa.String(), nullable=True))
    if not _column_exists("orders", "attributed_user_id"):
        op.add_column("orders", sa.Column("attributed_user_id", sa.Integer(), nullable=True))
    if not _fk_exists("orders", "attributed_user_id"):
        op.create_foreign_key(op.f("fk_orders_attributed_user_id_users"), "orders", "users", ["attributed_user_id"], ["id"], ondelete="SET NULL")
    if not _unique_exists("orders", "uq_orders_restaurant_idempotency_key"):
        op.create_unique_constraint(
            "uq_orders_restaurant_idempotency_key", "orders", ["restaurant_id", "idempotency_key"]
        )

    # 3. order_items: void + notes support (POS/KDS,
    if not _column_exists("order_items", "is_voided"):
        op.add_column("order_items", sa.Column("is_voided", sa.Boolean(), nullable=True))
    if not _column_exists("order_items", "void_reason"):
        op.add_column("order_items", sa.Column("void_reason", sa.String(), nullable=True))
    if not _column_exists("order_items", "notes"):
        op.add_column("order_items", sa.Column("notes", sa.String(), nullable=True))

    # 4. stock_movements: user attribution (retired local 029; shrinkage audit trail
    if not _column_exists("stock_movements", "user_id"):
        op.add_column("stock_movements", sa.Column("user_id", sa.Integer(), nullable=True))
    if not _fk_exists("stock_movements", "user_id"):
        op.create_foreign_key(op.f("fk_stock_movements_user_id_users"), "stock_movements", "users", ["user_id"], ["id"], ondelete="SET NULL")

    # 5. inventory_items: cost price for margin analysis (this branch's model field: cost_per_unit
    if not _column_exists("inventory_items", "cost_per_unit"):
        op.add_column("inventory_items", sa.Column("cost_per_unit", sa.Float(), nullable=True))


def downgrade() -> None:
    # Reverse in the reverse order (all guarded so a partial upgrade can be unwound
    if _column_exists("inventory_items", "cost_per_unit"):
        op.drop_column("inventory_items", "cost_per_unit")
    if _fk_exists("stock_movements", "user_id"):
        op.drop_constraint(op.f("fk_stock_movements_user_id_users"), "stock_movements", type_="foreignkey")
    if _column_exists("stock_movements", "user_id"):
        op.drop_column("stock_movements", "user_id")
    if _column_exists("order_items", "notes"):
        op.drop_column("order_items", "notes")
    if _column_exists("order_items", "void_reason"):
        op.drop_column("order_items", "void_reason")
    if _column_exists("order_items", "is_voided"):
        op.drop_column("order_items", "is_voided")
    if _unique_exists("orders", "uq_orders_restaurant_idempotency_key"):
        op.drop_constraint("uq_orders_restaurant_idempotency_key", "orders", type_="unique")
    if _fk_exists("orders", "attributed_user_id"):
        op.drop_constraint(op.f("fk_orders_attributed_user_id_users"), "orders", type_="foreignkey")
    for _col in ["attributed_user_id", "idempotency_key", "service_charge_cents", "tax_cents", "refund_reason", "refund_cents", "void_reason", "discount_reason", "discount_cents"]:
        if _column_exists("orders", _col):
            op.drop_column("orders", _col)
    if _column_exists("users", "display_name"):
        op.drop_column("users", "display_name")
    if (_column_exists("users", "pin_hash")and not _column_exists("users", "hashed_pin")):
        op.alter_column("users", "pin_hash", new_column_name="hashed_pin")