"""add stock_movements.user_id — attribution for receive/adjust (audit finding)

Revision ID: 029_add_stock_movement_user_id
Revises: 028_add_order_attributed_user_id
Create Date: 2026-08-03 00:00:00.000000

Adds stock_movements.user_id (nullable FK -> users.id, ON DELETE SET NULL).

Why: POST /inventory/{id}/receive and /adjust are open to any authenticated
user — deliberately, since logging a delivery or writing off waste is normal
floor work rather than an admin task. But StockMovement recorded only
item/type/quantity/reason, so a negative adjustment with a free-text reason
was completely anonymous. That is the textbook shrinkage vector, and it sat
directly beneath the profit-leak and portion-drift detection this product
sells: the analytics could see stock disappear but never who wrote it off.

The fix is attribution, not restriction — locking STAFF out of adjustments
would break legitimate kitchen workflow. Same shape as
Order.attributed_user_id (migration 028).

Nullable: pre-existing rows and system-generated movements (sales depletion)
carry no user. Idempotent via inspector column checks, matching prior
migrations; batch_alter_table for the SQLite ALTER-TABLE limitation
documented in 003_add_mpesa_fields_to_orders.py.
"""

from alembic import op
import sqlalchemy as sa

revision = "029_add_stock_movement_user_id"
down_revision = "028_add_order_attributed_user_id"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in sa.inspect(op.get_bind()).get_columns(table_name))


def upgrade():
    if not _column_exists("stock_movements", "user_id"):
        # Column + FK in one batch op — see 028's upgrade() for why a separate
        # top-level create_foreign_key() doesn't survive SQLite reflection.
        with op.batch_alter_table("stock_movements") as batch_op:
            batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_stock_movements_user_id",
                "users",
                ["user_id"], ["id"],
                ondelete="SET NULL",
            )


def downgrade():
    # No explicit drop_constraint — SQLite doesn't expose named FK constraints
    # through reflection (see 028's downgrade for the verified failure mode).
    # Dropping the column that carries the FK is sufficient on both dialects.
    with op.batch_alter_table("stock_movements") as batch_op:
        batch_op.drop_column("user_id")
