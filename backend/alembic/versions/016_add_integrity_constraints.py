"""add CHECK and composite-unique data-integrity constraints

Revision ID: 016_add_integrity_constraints
Revises: 015_add_fk_indexes
Create Date: 2026-07-10 00:00:00.000000

Run with: alembic upgrade head

Pushes invariants the app relies on down into the database, so a bug (or a
direct SQL edit) can't persist impossible data: non-negative money, positive
quantities/party sizes, and one table-number per restaurant.

DEPLOY SAFETY IS THE PRIMARY CONCERN. The container runs `alembic upgrade head`
at startup, so a migration that fails aborts the boot. Therefore:

  • Postgres CHECK constraints are added `NOT VALID`: the constraint applies to
    all new/updated rows immediately but existing rows are NOT scanned, so the
    migration can never fail on legacy data. Validate later at leisure with
    `ALTER TABLE ... VALIDATE CONSTRAINT ...` (safe, online).
  • The composite UNIQUE is guarded: if any duplicate (restaurant_id,
    table_number) already exists it is logged and SKIPPED rather than failing
    the deploy. Reconcile the dupes, then re-run.
  • On SQLite (tests / local) this migration is a NO-OP: SQLite can't ALTER TABLE
    ADD CONSTRAINT, and fresh SQLite DBs already carry these constraints from
    models.py via create_all(). Idempotent (name checks) on every dialect.
"""

import logging

from alembic import op
import sqlalchemy as sa

revision = "016_add_integrity_constraints"
down_revision = "015_add_fk_indexes"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.016")

# (constraint_name, table, boolean SQL expression)
_CHECKS = [
    ("ck_orders_total_nonneg",        "orders",        "total >= 0"),
    ("ck_order_items_qty_pos",        "order_items",   "quantity > 0"),
    ("ck_order_items_price_nonneg",   "order_items",   "unit_price >= 0"),
    ("ck_menu_items_price_nonneg",    "menu_items",    "price >= 0"),
    ("ck_menu_items_cost_nonneg",     "menu_items",    "cost_price >= 0"),
    ("ck_reservations_party_pos",     "reservations",  "party_size > 0"),
]

_UNIQUE = ("uq_tables_restaurant_number", "tables", ["restaurant_id", "table_number"])


def _existing_check_names(inspector, table: str) -> set[str]:
    try:
        return {c["name"] for c in inspector.get_check_constraints(table) if c.get("name")}
    except (NotImplementedError, Exception):
        return set()


def _existing_unique_names(inspector, table: str) -> set[str]:
    try:
        return {c["name"] for c in inspector.get_unique_constraints(table) if c.get("name")}
    except (NotImplementedError, Exception):
        return set()


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite/others: create_all already carries these (models.py). No-op.
        return

    inspector = sa.inspect(bind)

    for name, table, expr in _CHECKS:
        if not inspector.has_table(table):
            continue
        if name in _existing_check_names(inspector, table):
            continue
        # NOT VALID → applies to new rows only; never scans/legacy-fails the deploy.
        op.execute(f'ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expr}) NOT VALID')

    # Composite UNIQUE — guard against existing duplicates so we never abort boot.
    uname, utable, ucols = _UNIQUE
    if inspector.has_table(utable) and uname not in _existing_unique_names(inspector, utable):
        dupes = bind.execute(sa.text(
            f"SELECT COUNT(*) FROM (SELECT {', '.join(ucols)} FROM {utable} "
            f"GROUP BY {', '.join(ucols)} HAVING COUNT(*) > 1) d"
        )).scalar()
        if dupes and dupes > 0:
            logger.warning(
                "[016] Skipping %s: %d duplicate (%s) group(s) exist. "
                "Reconcile duplicates then re-run to enforce uniqueness.",
                uname, dupes, ", ".join(ucols),
            )
        else:
            op.create_unique_constraint(uname, utable, ucols)


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    uname, utable, _ = _UNIQUE
    if uname in _existing_unique_names(inspector, utable):
        op.drop_constraint(uname, utable, type_="unique")
    for name, table, _expr in _CHECKS:
        if name in _existing_check_names(inspector, table):
            op.drop_constraint(name, table, type_="check")
