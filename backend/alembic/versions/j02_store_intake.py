"""Store intake: zones, buying units, question answers, running costs, balances.

Revision ID: j02_store_intake
Revises: j01_storekeeper_foundation
"""
from alembic import op
import sqlalchemy as sa

revision = "j02_store_intake"
down_revision = "j01_storekeeper_foundation"
branch_labels = None
depends_on = None


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table):
    if table not in _tables():
        return set()
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    if "stock_zones" not in _tables():
        op.create_table(
            "stock_zones",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("kind", sa.String(), nullable=False, server_default="store"),
            sa.UniqueConstraint("restaurant_id", "name", name="uq_stock_zone_name"),
        )
        op.create_index("ix_stock_zones_id", "stock_zones", ["id"])
        op.create_index("ix_stock_zones_restaurant", "stock_zones", ["restaurant_id"])

    item_cols = _columns("inventory_items")
    if "buying_unit" not in item_cols:
        op.add_column("inventory_items", sa.Column("buying_unit", sa.String(), nullable=True))
    if "units_per_buy" not in item_cols:
        op.add_column("inventory_items", sa.Column("units_per_buy", sa.Float(), nullable=True))
    if "yield_fraction" not in item_cols:
        op.add_column(
            "inventory_items",
            sa.Column("yield_fraction", sa.Float(), nullable=False, server_default="1"),
        )
    if "zone_id" not in item_cols:
        op.add_column(
            "inventory_items",
            sa.Column("zone_id", sa.Integer(), sa.ForeignKey("stock_zones.id"), nullable=True),
        )
    if "brings" not in _columns("suppliers"):
        op.add_column(
            "suppliers",
            sa.Column("brings", sa.String(), nullable=False, server_default=""),
        )
    if "arrival" not in _columns("suppliers"):
        op.add_column(
            "suppliers",
            sa.Column("arrival", sa.String(), nullable=False, server_default=""),
        )

    if "staff_setup_answers" not in _tables():
        op.create_table(
            "staff_setup_answers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("question_id", sa.String(), nullable=False),
            sa.Column("value", sa.String(), nullable=False),
            sa.Column("label", sa.String(), nullable=False, server_default=""),
            sa.Column("opens", sa.String(), nullable=True),
            sa.Column("unlocks", sa.String(), nullable=True),
            sa.Column("delegated", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("delegate_to", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_staff_setup_answers_id", "staff_setup_answers", ["id"])
        op.create_index("ix_staff_setup_answers_user", "staff_setup_answers", ["user_id"])
        op.create_index("ix_staff_setup_answers_restaurant", "staff_setup_answers", ["restaurant_id"])

    if "running_costs" not in _tables():
        op.create_table(
            "running_costs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("label", sa.String(), nullable=False),
            sa.Column("amount_cents", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_running_costs_id", "running_costs", ["id"])
        op.create_index("ix_running_costs_restaurant", "running_costs", ["restaurant_id"])

    if "stock_balances" not in _tables():
        op.create_table(
            "stock_balances",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("inventory_item_id", sa.Integer(), sa.ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False),
            sa.Column("zone_id", sa.Integer(), sa.ForeignKey("stock_zones.id"), nullable=False),
            sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
            sa.UniqueConstraint("inventory_item_id", "zone_id", name="uq_stock_balance_item_zone"),
        )
        op.create_index("ix_stock_balances_id", "stock_balances", ["id"])
        op.create_index("ix_stock_balances_restaurant", "stock_balances", ["restaurant_id"])


def downgrade():
    if "stock_balances" in _tables():
        op.drop_table("stock_balances")
    if "running_costs" in _tables():
        op.drop_table("running_costs")
    if "staff_setup_answers" in _tables():
        op.drop_table("staff_setup_answers")
    item_cols = _columns("inventory_items")
    if "zone_id" in item_cols:
        op.drop_column("inventory_items", "zone_id")
    if "yield_fraction" in item_cols:
        op.drop_column("inventory_items", "yield_fraction")
    if "units_per_buy" in item_cols:
        op.drop_column("inventory_items", "units_per_buy")
    if "buying_unit" in item_cols:
        op.drop_column("inventory_items", "buying_unit")
    if "arrival" in _columns("suppliers"):
        op.drop_column("suppliers", "arrival")
    if "brings" in _columns("suppliers"):
        op.drop_column("suppliers", "brings")
    if "stock_zones" in _tables():
        op.drop_table("stock_zones")
