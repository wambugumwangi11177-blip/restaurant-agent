"""convert inventory_items.cost_per_unit from float KES to integer cents

Revision ID: 035_convert_inventory_cost_to_cents
Revises: 034_add_auth_tokens_and_email_verified
Create Date: 2026-07-17 00:00:00.000000

Run with: alembic upgrade head

Fixes the money-as-float bug flagged in the 2026-07-17 database audit:
InventoryItem.cost_per_unit was a Float storing whole KES, the only money
column in the schema not stored as integer cents (PurchaseOrder.cost_per_unit
and .total_cost already are). Renames the physical column to
cost_per_unit_cents and backs models.InventoryItem.cost_per_unit with a
Python @property that converts transparently — every existing consumer
(schemas.py, routers/inventory.py, ai/reorder.py, ai/inventory_predictor.py,
populate_production.py, the frontend's `KES {cost_per_unit}` display) reads
and writes `.cost_per_unit` as a plain attribute and keeps working in KES
unchanged, since none of them query/filter/order_by on this column at the
SQL level (verified — only ORM attribute access, no
`.filter(InventoryItem.cost_per_unit ...)` anywhere in the codebase).

Idempotent via inspector checks, same posture as 033/034.
"""

from alembic import op
import sqlalchemy as sa

revision = "035_convert_inventory_cost_to_cents"
down_revision = "034_add_auth_tokens_and_email_verified"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in _insp().get_columns(table_name))


def upgrade():
    if not _column_exists("inventory_items", "cost_per_unit_cents"):
        op.add_column(
            "inventory_items",
            sa.Column("cost_per_unit_cents", sa.Integer(), nullable=True, server_default="0"),
        )
        op.execute(
            "UPDATE inventory_items "
            "SET cost_per_unit_cents = ROUND(COALESCE(cost_per_unit, 0) * 100)::integer"
        )

    if _column_exists("inventory_items", "cost_per_unit"):
        op.drop_column("inventory_items", "cost_per_unit")


def downgrade():
    if not _column_exists("inventory_items", "cost_per_unit"):
        op.add_column(
            "inventory_items",
            sa.Column("cost_per_unit", sa.Float(), nullable=True, server_default="0"),
        )
        op.execute(
            "UPDATE inventory_items "
            "SET cost_per_unit = COALESCE(cost_per_unit_cents, 0) / 100.0"
        )

    if _column_exists("inventory_items", "cost_per_unit_cents"):
        op.drop_column("inventory_items", "cost_per_unit_cents")
