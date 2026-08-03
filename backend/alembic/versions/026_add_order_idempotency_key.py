"""add orders.idempotency_key for the POS offline queue (tech-debt D15)

Revision ID: 026_add_order_idempotency_key
Revises: 025_add_user_is_active
Create Date: 2026-08-02 00:00:00.000000

Adds orders.idempotency_key (string, nullable), unique per (restaurant_id,
idempotency_key) — NOT globally unique, deliberately: this key is
client-generated (crypto.randomUUID() in the POS offline queue), unlike
mpesa_checkout_request_id which is genuinely global because Safaricom issues
it. A same-key collision between two different tenants must never fail one
of their orders with an IntegrityError. create_order() looks the key up
scoped to the caller's own restaurant_id and returns the existing order
unchanged on a replay instead of inserting a duplicate. Nullable/unset for
every order not submitted through that flow (unchanged behavior); Postgres
and SQLite both allow multiple NULLs through a unique index.

batch_alter_table used for the same SQLite ALTER-TABLE-limitation reason
documented in 003_add_mpesa_fields_to_orders.py.
"""

from alembic import op
import sqlalchemy as sa

revision = "026_add_order_idempotency_key"
down_revision = "025_add_user_is_active"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in sa.inspect(op.get_bind()).get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(idx["name"] == index_name for idx in sa.inspect(op.get_bind()).get_indexes(table_name))


def upgrade() -> None:
    if not _column_exists("orders", "idempotency_key"):
        op.add_column("orders", sa.Column("idempotency_key", sa.String(), nullable=True))
    if not _index_exists("orders", "uq_orders_restaurant_idempotency_key"):
        op.create_index(
            "uq_orders_restaurant_idempotency_key",
            "orders",
            ["restaurant_id", "idempotency_key"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_index("uq_orders_restaurant_idempotency_key")
        batch_op.drop_column("idempotency_key")
