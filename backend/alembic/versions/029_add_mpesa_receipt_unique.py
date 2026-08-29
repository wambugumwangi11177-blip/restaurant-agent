"""partial unique index on orders.mpesa_receipt

Revision ID: 029_add_mpesa_receipt_unique
Revises: 028_add_fk_ondelete_policy
Create Date: 2026-07-16 00:00:00.000000

Run with: alembic upgrade head

orders.mpesa_checkout_request_id (the STK-push request we made) is already
unique, but orders.mpesa_receipt (the Safaricom transaction reference that
comes BACK) was not — a webhook retry racing across two different orders, or a
future integration bug, could record the same M-Pesa receipt as the settlement
for two separate orders with nothing in the schema to catch it. This closes
that gap with a partial unique index (WHERE mpesa_receipt IS NOT NULL, so
unpaid orders — mpesa_receipt IS NULL — never collide with each other).

routers/webhooks.py's _settle_order_once() is updated in the same change to
catch the resulting IntegrityError as a non-fatal, logged event: the endpoint
always ACKs Safaricom with 200 regardless of settlement outcome, so this must
never surface as an error response.

DEPLOY SAFETY: guarded exactly like migration 016 — count existing duplicate
receipts first and SKIP (log + leave unenforced) rather than fail the deploy
if any already exist, so a legacy data issue can never abort boot. No-op on
SQLite (tests): create_all() already carries the same partial index there via
models.py's Index(..., sqlite_where=...).
"""

import logging

from alembic import op
import sqlalchemy as sa

revision = "029_add_mpesa_receipt_unique"
down_revision = "028_add_fk_ondelete_policy"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.029")

_INDEX_NAME = "uq_orders_mpesa_receipt"


def _existing_index_names(inspector, table):
    return {ix["name"] for ix in inspector.get_indexes(table)}


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    inspector = sa.inspect(bind)
    if not inspector.has_table("orders"):
        return
    if _INDEX_NAME in _existing_index_names(inspector, "orders"):
        return

    dupes = bind.execute(sa.text(
        "SELECT COUNT(*) FROM (SELECT mpesa_receipt FROM orders "
        "WHERE mpesa_receipt IS NOT NULL "
        "GROUP BY mpesa_receipt HAVING COUNT(*) > 1) d"
    )).scalar()
    if dupes and dupes > 0:
        logger.warning(
            "[029] Skipping %s: %d duplicate mpesa_receipt group(s) exist. "
            "Reconcile duplicates then re-run to enforce uniqueness.",
            _INDEX_NAME, dupes,
        )
        return

    op.execute(
        sa.text(
            f'CREATE UNIQUE INDEX {_INDEX_NAME} ON orders (mpesa_receipt) '
            f'WHERE mpesa_receipt IS NOT NULL'
        )
    )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    if inspector.has_table("orders") and _INDEX_NAME in _existing_index_names(inspector, "orders"):
        op.drop_index(_INDEX_NAME, table_name="orders")