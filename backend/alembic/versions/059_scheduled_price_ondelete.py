"""Cascade scheduled prices when a dish is deleted.

Revision ID: 059_scheduled_price_ondelete
Revises: 058_eleven_workflows

Migration 058 created scheduled_menu_prices.menu_item_id with no ON DELETE
clause. Deleting a dish that only had scheduled prices then failed the menu
delete path, which reports every integrity error as "has order history".
This does not rewrite 058. Scheduled prices have no meaning without the dish,
same as pricing recommendations (migration 028), so the delete cascades.
"""
from alembic import op
import sqlalchemy as sa

revision = "059_scheduled_price_ondelete"
down_revision = "058_eleven_workflows"
branch_labels = None
depends_on = None


def _fk_for_column(inspector, table, column):
    for fk in inspector.get_foreign_keys(table):
        if fk.get("constrained_columns") == [column]:
            return fk
    return None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    if not inspector.has_table("scheduled_menu_prices"):
        return
    fk = _fk_for_column(inspector, "scheduled_menu_prices", "menu_item_id")
    current = (fk or {}).get("options", {}).get("ondelete")
    if current and current.upper() == "CASCADE":
        return
    if fk and fk.get("name"):
        op.drop_constraint(fk["name"], "scheduled_menu_prices", type_="foreignkey")
    op.create_foreign_key(
        "fk_scheduled_menu_prices_menu_item_id_menu_items",
        "scheduled_menu_prices", "menu_items", ["menu_item_id"], ["id"], ondelete="CASCADE",
    )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    if not inspector.has_table("scheduled_menu_prices"):
        return
    fk = _fk_for_column(inspector, "scheduled_menu_prices", "menu_item_id")
    if fk and fk.get("name"):
        op.drop_constraint(fk["name"], "scheduled_menu_prices", type_="foreignkey")
    op.create_foreign_key(
        "fk_scheduled_menu_prices_menu_item_id_menu_items",
        "scheduled_menu_prices", "menu_items", ["menu_item_id"], ["id"],
    )
