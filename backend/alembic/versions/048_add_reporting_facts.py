"""048 reporting facts — daily sales rollups + a covering index for the report join.

Created 2026-09-19. routers/reports.py aggregated straight off `orders` and
`order_items`. Measured on a seeded 300,000-order / 900,000-line-item dataset,
the yearly report cost ~2.5 s of database work. Two changes here:

1. ix_order_items_order_covering — carries menu_item_id, quantity and unit_price
   alongside order_id so the reporting join can aggregate from the index instead
   of visiting each row. Yearly _top_items 1841 ms -> 1223 ms on its own.

2. daily_sales_facts / daily_item_sales_facts — the dimensional rollup. Two
   grains because an order has many line items: counting orders from an
   item-grain table would multiply-count, so revenue/order-count live at
   (restaurant, day) and quantity/sales at (restaurant, day, menu item).
   With these, yearly _top_items drops to 6.3 ms and _summarize to 0.7 ms.

`business_date` is the Africa/Nairobi calendar day, matching _EAT_OFFSET in
routers/reports.py. These tables are a CACHE of a query, never a source of
truth — backend/reporting/rollup.py re-aggregates a trailing window and every
read falls back to the live query when coverage is incomplete.
"""
revision = "048_add_reporting_facts"
down_revision = "047_attention_decisions"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # init_db() runs Base.metadata.create_all() before Alembic on a fresh DB, so
    # these may already exist — plain CREATE TABLE would crash the deploy with
    # DuplicateTable, the failure migration 047 documents. IF NOT EXISTS
    # throughout; the column lists match models.py exactly.
    pk = "SERIAL NOT NULL" if _is_postgres() else "INTEGER NOT NULL"
    big = "BIGINT" if _is_postgres() else "INTEGER"

    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS daily_sales_facts (
            id {pk},
            restaurant_id INTEGER NOT NULL REFERENCES restaurants (id) ON DELETE CASCADE,
            business_date DATE NOT NULL,
            revenue_cents {big} NOT NULL DEFAULT 0,
            order_count INTEGER NOT NULL DEFAULT 0,
            built_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT uq_daily_sales_fact_day UNIQUE (restaurant_id, business_date),
            CONSTRAINT ck_daily_sales_fact_revenue_nonneg CHECK (revenue_cents >= 0),
            CONSTRAINT ck_daily_sales_fact_count_nonneg CHECK (order_count >= 0)
        )
        """
    )
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS daily_item_sales_facts (
            id {pk},
            restaurant_id INTEGER NOT NULL REFERENCES restaurants (id) ON DELETE CASCADE,
            business_date DATE NOT NULL,
            menu_item_id INTEGER NOT NULL REFERENCES menu_items (id) ON DELETE RESTRICT,
            qty INTEGER NOT NULL DEFAULT 0,
            sales_cents {big} NOT NULL DEFAULT 0,
            built_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT uq_daily_item_sales_fact_day_item
                UNIQUE (restaurant_id, business_date, menu_item_id),
            CONSTRAINT ck_daily_item_sales_fact_qty_nonneg CHECK (qty >= 0),
            CONSTRAINT ck_daily_item_sales_fact_sales_nonneg CHECK (sales_cents >= 0)
        )
        """
    )

    for stmt in (
        "CREATE INDEX IF NOT EXISTS ix_daily_sales_facts_id ON daily_sales_facts (id)",
        "CREATE INDEX IF NOT EXISTS ix_daily_sales_facts_restaurant_date "
        "ON daily_sales_facts (restaurant_id, business_date)",
        "CREATE INDEX IF NOT EXISTS ix_daily_item_sales_facts_id ON daily_item_sales_facts (id)",
        "CREATE INDEX IF NOT EXISTS ix_daily_item_sales_facts_restaurant_date "
        "ON daily_item_sales_facts (restaurant_id, business_date)",
        # The covering index. Deliberately created last: on a large order_items
        # table this is the slow statement in the migration, and everything above
        # is already durable if the deploy is interrupted here.
        "CREATE INDEX IF NOT EXISTS ix_order_items_order_covering "
        "ON order_items (order_id, menu_item_id, quantity, unit_price)",
    ):
        op.execute(stmt)


def downgrade() -> None:
    # Facts are a derived cache — dropping them loses no source data, and
    # reporting/rollup.py falls back to the live query the moment coverage is
    # gone, so a downgrade degrades report latency and nothing else.
    op.execute("DROP INDEX IF EXISTS ix_order_items_order_covering")
    op.execute("DROP TABLE IF EXISTS daily_item_sales_facts")
    op.execute("DROP TABLE IF EXISTS daily_sales_facts")
