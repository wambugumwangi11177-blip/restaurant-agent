"""add mpesa checkout correlation + receipt to orders

Revision ID: 003_add_mpesa_fields_to_orders
Revises: 002_add_agent_message_token_usage
Create Date: 2026-07-07 00:00:00.000000

Run with: alembic upgrade head

Real M-Pesa STK push/callback wiring (directives/012_agentic_roadmap.md, Phase 1).
mpesa_checkout_request_id is the correlation key between an STK push we initiate
and the Safaricom callback that confirms/rejects it. UNIQUE prevents two orders
from ever being matched to the same checkout request.

Idempotent via inspector column/index checks (see 001_add_agent_tables.py's
docstring for why raw "IF NOT EXISTS" SQL isn't used here).
"""

from alembic import op
import sqlalchemy as sa

revision = "003_add_mpesa_fields_to_orders"
down_revision = "002_add_agent_message_token_usage"
branch_labels = None
depends_on = None


def _get_inspector():
    # op.get_bind() is deprecated in Alembic + SQLAlchemy 2.x;
    # op.get_context().connection is the supported replacement.
    return sa.inspect(op.get_context().connection)


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in _get_inspector().get_columns(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(idx["name"] == index_name for idx in _get_inspector().get_indexes(table_name))


def upgrade() -> None:
    if not _column_exists("orders", "mpesa_checkout_request_id"):
        op.add_column("orders", sa.Column("mpesa_checkout_request_id", sa.String(), nullable=True))
    if not _column_exists("orders", "mpesa_receipt"):
        op.add_column("orders", sa.Column("mpesa_receipt", sa.String(), nullable=True))
    if not _index_exists("orders", "ix_orders_mpesa_checkout_request_id"):
        op.create_index(
            "ix_orders_mpesa_checkout_request_id",
            "orders",
            ["mpesa_checkout_request_id"],
            unique=True,
        )


def downgrade() -> None:
    # batch_alter_table: SQLite's native ALTER TABLE DROP COLUMN has known
    # limitations when the column is part of an index (fails even after the
    # index is dropped in a separate statement, verified while testing this
    # migration) — batch mode recreates the table safely instead. On Postgres
    # (production) this transparently falls back to plain ALTER statements.
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_index("ix_orders_mpesa_checkout_request_id")
        batch_op.drop_column("mpesa_receipt")
        batch_op.drop_column("mpesa_checkout_request_id")