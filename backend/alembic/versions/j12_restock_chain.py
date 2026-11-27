"""Restock routing, PO requester, staple caps."""
import sqlalchemy as sa
from alembic import op

revision = "j12_restock_chain"
down_revision = "j11_review_handovers_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("restaurants")} if "restaurants" in inspector.get_table_names() else set()
    if "restock_routing_mode" not in cols:
        op.add_column(
            "restaurants",
            sa.Column("restock_routing_mode", sa.String(), nullable=False, server_default="owner_approves"),
        )
    if "staple_caps_json" not in cols:
        op.add_column("restaurants", sa.Column("staple_caps_json", sa.Text(), nullable=False, server_default="{}"))

    po_cols = {c["name"] for c in inspector.get_columns("purchase_orders")} if "purchase_orders" in inspector.get_table_names() else set()
    if "ordered_by_user_id" not in po_cols:
        op.add_column("purchase_orders", sa.Column("ordered_by_user_id", sa.Integer(), nullable=True))
    if "requested_by_user_id" not in po_cols:
        op.add_column("purchase_orders", sa.Column("requested_by_user_id", sa.Integer(), nullable=True))

    prog_cols = {c["name"] for c in inspector.get_columns("staff_setup_progress")} if "staff_setup_progress" in inspector.get_table_names() else set()
    if "opening_stock_completed_at" not in prog_cols:
        op.add_column("staff_setup_progress", sa.Column("opening_stock_completed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("staff_setup_progress", "opening_stock_completed_at")
    op.drop_column("purchase_orders", "requested_by_user_id")
    op.drop_column("purchase_orders", "ordered_by_user_id")
    op.drop_column("restaurants", "staple_caps_json")
    op.drop_column("restaurants", "restock_routing_mode")