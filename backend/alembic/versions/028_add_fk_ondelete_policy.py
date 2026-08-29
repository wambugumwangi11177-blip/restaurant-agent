"""explicit ON DELETE policy for FKs with a live delete endpoint or pure-owned children

Revision ID: 028_add_fk_ondelete_policy
Revises: 027_add_par_level_reordering
Create Date: 2026-07-16 00:00:00.000000

Run with: alembic upgrade head

Every FK in this schema relied on Postgres's implicit NO ACTION/RESTRICT
default — deleting a MenuItem/InventoryItem/Supplier that has order/stock/
purchase history threw an unhandled IntegrityError (500) instead of a clean
409 (see routers/menu.py, routers/inventory.py, routers/suppliers.py), and the
only cascade anywhere in the app was ORM-level (Order.items), which does
nothing for a raw SQL delete.

This migration makes the policy explicit for the FKs that actually matter —
parents with a live delete endpoint, or pure-owned child rows with no
independent value once the parent is gone — by dropping and recreating each
named FK constraint with an explicit ON DELETE clause.

Scope is deliberate: everything else (Tenant/Restaurant/User/Organization/
Region/Table/etc.) keeps the implicit RESTRICT default, because nothing in the
app hard-deletes those parents today — they use is_active-style soft delete
instead. See the ondelete= comments next to each column in models.py for the
per-relationship reasoning.

DEPLOY SAFETY: no-op on SQLite (tests / local) — SQLite cannot ALTER a FK
constraint in place, and a fresh SQLite DB already carries these policies via
models.py's `ondelete=` at create_all() time. On Postgres, each constraint is
looked up by introspection (never assumed by name — naming can vary), and only
touched if it doesn't already match. ON DELETE changes are metadata-only (no
existing data can violate them), so unlike migration 016's CHECK constraints
this never needs a NOT VALID / duplicate-scan guard.
"""

from alembic import op
import sqlalchemy as sa

revision = "028_add_fk_ondelete_policy"
down_revision = "027_add_par_level_reordering"
branch_labels = None
depends_on = None


# (table, column, ref_table, ref_column, ondelete)
_POLICY = [
    ("order_items",             "order_id",           "orders",           "id", "CASCADE"),
    ("order_items",             "menu_item_id",        "menu_items",       "id", "RESTRICT"),
    ("prep_times",               "order_item_id",       "order_items",      "id", "CASCADE"),
    ("stock_movements",          "inventory_item_id",   "inventory_items",  "id", "RESTRICT"),
    ("pricing_recommendations",  "menu_item_id",        "menu_items",       "id", "CASCADE"),
    ("menu_ingredients",         "menu_item_id",        "menu_items",       "id", "CASCADE"),
    ("menu_ingredients",         "inventory_item_id",   "inventory_items",  "id", "CASCADE"),
    ("purchase_orders",          "supplier_id",         "suppliers",        "id", "RESTRICT"),
    ("purchase_orders",          "inventory_item_id",   "inventory_items",  "id", "SET NULL"),
    ("stock_transfers",          "inventory_item_id",   "inventory_items",  "id", "RESTRICT"),
    ("stock_counts",             "inventory_item_id",   "inventory_items",  "id", "RESTRICT"),
    ("workflow_steps",           "run_id",              "workflow_runs",    "id", "CASCADE"),
]


def _fk_for_column(inspector, table, column):
    for fk in inspector.get_foreign_keys(table):
        if fk.get("constrained_columns") == [column]:
            return fk
    return None


def _constraint_name(table, column, ref_table):
    return f"fk_{table}_{column}_{ref_table}"


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)

    for table, column, ref_table, ref_column, ondelete in _POLICY:
        if not inspector.has_table(table):
            continue
        fk = _fk_for_column(inspector, table, column)
        current = (fk or {}).get("options", {}).get("ondelete")
        if current and current.upper() == ondelete:
            continue  # already correct
        if fk and fk.get("name"):
            op.drop_constraint(fk["name"], table, type_="foreignkey")
        op.create_foreign_key(
            _constraint_name(table, column, ref_table),
            table, ref_table, [column], [ref_column], ondelete=ondelete,
        )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)

    for table, column, ref_table, ref_column, _ondelete in _POLICY:
        if not inspector.has_table(table):
            continue
        fk = _fk_for_column(inspector, table, column)
        if fk and fk.get("name"):
            op.drop_constraint(fk["name"], table, type_="foreignkey")
        op.create_foreign_key(
            _constraint_name(table, column, ref_table),
            table, ref_table, [column], [ref_column],
        )
