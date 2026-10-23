"""Recipe yield, receiving units, invoice references and retry keys. Additive; old rows keep their meaning."""
from alembic import op
import sqlalchemy as sa

revision = "057_eleven_readiness"
down_revision = "056_mpesa_match_setting"
branch_labels = None
depends_on = None

FIELDS = {
    "restaurant_settings": [sa.Column("sales_drop_flag_pct", sa.Float(), nullable=False, server_default="15")],
    "menu_ingredients": [sa.Column("yield_fraction", sa.Float(), nullable=False, server_default="1")],
    "inventory_items": [sa.Column("buying_unit", sa.String(40), nullable=False, server_default=""),
                        sa.Column("buying_unit_factor", sa.Float(), nullable=False, server_default="1")],
    "purchase_orders": [sa.Column("invoice_ref", sa.String(255), nullable=True)],
    "expenses": [sa.Column("entry_key", sa.String(120), nullable=True)],
    "cash_drawer_counts": [sa.Column("entry_key", sa.String(120), nullable=True)],
}

def upgrade():
    offline = op.get_context().as_sql
    for table, columns in FIELDS.items():
        existing = set() if offline else {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)
    for table in ("expenses", "cash_drawer_counts"):
        name = f"uq_{table}_entry_key"
        indexes = set() if offline else {i['name'] for i in sa.inspect(op.get_bind()).get_indexes(table)}
        if name not in indexes:
            op.create_index(name, table, ["entry_key"], unique=True)

def downgrade():
    for table in ("expenses", "cash_drawer_counts"):
        op.drop_index(f"uq_{table}_entry_key", table_name=table)
    for table, columns in reversed(list(FIELDS.items())):
        with op.batch_alter_table(table) as batch:
            for column in reversed(columns):
                batch.drop_column(column.name)
