"""add indexes on foreign-key and hot-lookup columns

Revision ID: 015_add_fk_indexes
Revises: 014_add_reservation_reminder_sent_at
Create Date: 2026-07-10 00:00:00.000000

Run with: alembic upgrade head

Postgres does NOT auto-create an index for a FOREIGN KEY column. Every
tenant-scoped query in this app filters on `restaurant_id` (and joins on
`order_id`/`menu_item_id`/etc.), so without these indexes each of those does a
sequential scan that degrades as data grows. This adds covering indexes for the
FK/hot-lookup columns on the growing tables that did not already have one.

Tables that already ship composite indexes in __table_args__
(pricing_recommendations, agent_messages, memory_events, token_usage,
customer_consents, customer_feedback) and unique-indexed columns
(orders.mpesa_checkout_request_id, customer_optouts.customer_phone,
users.email) are intentionally omitted — they are already covered.

Idempotent: each index is created only if a same-named index is not already
present (inspector check), so a re-run or a fresh create_all()-seeded DB won't
error. Works on both SQLite (tests) and Postgres (prod).
"""

from alembic import op
import sqlalchemy as sa

revision = "015_add_fk_indexes"
down_revision = "014_add_reservation_reminder_sent_at"
branch_labels = None
depends_on = None


# (index_name, table, [columns])
_INDEXES = [
    ("ix_menu_items_restaurant_id",          "menu_items",      ["restaurant_id"]),
    ("ix_orders_restaurant_created",         "orders",          ["restaurant_id", "created_at"]),
    ("ix_orders_restaurant_status",          "orders",          ["restaurant_id", "status"]),
    ("ix_orders_customer_phone",             "orders",          ["customer_phone"]),
    ("ix_order_items_order_id",              "order_items",     ["order_id"]),
    ("ix_order_items_menu_item_id",          "order_items",     ["menu_item_id"]),
    ("ix_inventory_items_restaurant_id",     "inventory_items", ["restaurant_id"]),
    ("ix_stock_movements_inventory_item_id", "stock_movements", ["inventory_item_id"]),
    ("ix_reservations_restaurant_date",      "reservations",    ["restaurant_id", "reservation_date"]),
    ("ix_reservations_customer_phone",       "reservations",    ["customer_phone"]),
    ("ix_reservations_table_id",             "reservations",    ["table_id"]),
    ("ix_prep_times_order_item_id",          "prep_times",      ["order_item_id"]),
    ("ix_tables_restaurant_id",              "tables",          ["restaurant_id"]),
    ("ix_users_tenant_id",                   "users",           ["tenant_id"]),
    ("ix_restaurants_tenant_id",             "restaurants",     ["tenant_id"]),
]


def _existing(inspector, table: str) -> set[str]:
    if not inspector.has_table(table):
        return set()
    return {ix["name"] for ix in inspector.get_indexes(table)}


def upgrade():
    inspector = sa.inspect(op.get_bind())
    for name, table, cols in _INDEXES:
        if not inspector.has_table(table):
            continue
        if name not in _existing(inspector, table):
            op.create_index(name, table, cols)


def downgrade():
    inspector = sa.inspect(op.get_bind())
    for name, table, _cols in _INDEXES:
        if name in _existing(inspector, table):
            op.drop_index(name, table_name=table)
