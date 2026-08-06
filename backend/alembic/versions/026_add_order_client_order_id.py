"""add orders.client_order_id (offline POS idempotency)

Revision ID: 026_add_order_client_order_id
Revises: 025_add_stock_counts
Create Date: 2026-08-06 00:00:00.000000

Run with: alembic upgrade head

Lets a replayed order create (the offline POS queue retrying a request it
can't confirm succeeded) be recognized as "already placed" instead of
creating a duplicate ticket and double-deducting stock. NULL for every order
placed while online; multiple NULLs are fine under this UNIQUE constraint on
both SQLite and Postgres. Idempotent, coexists with create_all() — same
pattern as every migration since 015.
"""

from alembic import op
import sqlalchemy as sa

revision = "026_add_order_client_order_id"
down_revision = "025_add_stock_counts"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _column_exists(table: str, column: str) -> bool:
    return column in [c["name"] for c in _insp().get_columns(table)]


def _constraint_exists(table: str, name: str) -> bool:
    insp = _insp()
    names = {c["name"] for c in insp.get_unique_constraints(table)}
    # SQLite surfaces some unique constraints as indexes instead.
    names |= {i["name"] for i in insp.get_indexes(table)}
    return name in names


def upgrade():
    if not _column_exists("orders", "client_order_id"):
        op.add_column("orders", sa.Column("client_order_id", sa.String(), nullable=True))
    if not _constraint_exists("orders", "uq_orders_restaurant_client_order_id"):
        op.create_unique_constraint(
            "uq_orders_restaurant_client_order_id", "orders",
            ["restaurant_id", "client_order_id"],
        )


def downgrade():
    if _constraint_exists("orders", "uq_orders_restaurant_client_order_id"):
        op.drop_constraint("uq_orders_restaurant_client_order_id", "orders", type_="unique")
    if _column_exists("orders", "client_order_id"):
        op.drop_column("orders", "client_order_id")
