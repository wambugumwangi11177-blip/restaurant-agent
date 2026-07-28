"""add NOT VALID tenant-scoping CHECKs and a partial-unique owner_phone index

Revision ID: 025_tenant_fk_and_owner_phone_integrity
Revises: 024_add_enterprise_hierarchy
Create Date: 2026-07-28 00:00:00.000000

Run with: alembic upgrade head

Two integrity gaps found in a full-stack audit:
  1. Several tenant-scoping FK columns (Order.restaurant_id,
     Reservation.restaurant_id, MenuItem.restaurant_id, Table.restaurant_id,
     InventoryItem.restaurant_id, Restaurant.tenant_id, User.tenant_id) are
     nullable in models.py — inconsistent with every newer table, which
     declares nullable=False.
  2. Restaurant.owner_phone has no unique constraint. routers/webhooks.py
     resolves an inbound WhatsApp message with
     `filter(Restaurant.owner_phone == normalized).first()`, so two
     restaurants sharing an owner_phone means one silently receives the
     other's WhatsApp messages.

DEPLOY SAFETY IS THE PRIMARY CONCERN, same as 016: the container runs
`alembic upgrade head` at startup, so a migration that raises aborts the
boot. Two deliberate departures from a "real" NOT NULL / CONCURRENTLY
migration, both explained in directives/tech-debt notes at deploy time:

  • NOT NULL is implemented as `CHECK (col IS NOT NULL) NOT VALID` rather than
    `ALTER COLUMN ... SET NOT NULL`. NOT VALID enforces on every new/updated
    row immediately, never scans existing rows, and cannot fail on dirty
    data — SET NOT NULL would table-scan and fail outright on a single
    existing NULL. Promoting to a real NOT NULL (VALIDATE CONSTRAINT + ALTER
    COLUMN) is a deliberate follow-up once execution_checks/preflight_025.py
    confirms prod is clean — not done here, since that promotion is the one
    step in this whole migration that could legitimately fail.
  • The owner_phone unique index is a plain CREATE UNIQUE INDEX, not
    CONCURRENTLY. `alembic/env.py` runs every migration inside one outer
    transaction (no `transaction_per_migration`), and CREATE INDEX
    CONCURRENTLY cannot run inside a transaction block — it would raise and
    crash the boot chain. `restaurants` is one row per pilot restaurant, so a
    plain index locks it for milliseconds; CONCURRENTLY buys nothing here.

Like 016, dirty data is logged and SKIPPED rather than failing the deploy —
run execution_checks/preflight_025.py against a real database BEFORE this
deploys to know in advance whether anything will be skipped (Alembic stamps
this revision as applied either way, so a skip here does not auto-retry on a
later `upgrade head` — a fresh migration would be needed to enforce a column
skipped today).

On SQLite (tests / local) this migration is a NO-OP: SQLite can't ALTER TABLE
ADD CONSTRAINT / CREATE UNIQUE INDEX the way this needs, and fresh SQLite DBs
already carry nullable=False + unique=True from models.py via create_all().
Idempotent (inspector name / index-existence checks) on every dialect.
"""

import logging

from alembic import op
import sqlalchemy as sa

revision = "025_tenant_fk_and_owner_phone_integrity"
down_revision = "024_add_enterprise_hierarchy"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.025")

# (constraint_name, table, column)
_NOT_NULL_CHECKS = [
    ("ck_users_tenant_id_not_null", "users", "tenant_id"),
    ("ck_restaurants_tenant_id_not_null", "restaurants", "tenant_id"),
    ("ck_tables_restaurant_id_not_null", "tables", "restaurant_id"),
    ("ck_menu_items_restaurant_id_not_null", "menu_items", "restaurant_id"),
    ("ck_inventory_items_restaurant_id_not_null", "inventory_items", "restaurant_id"),
    ("ck_orders_restaurant_id_not_null", "orders", "restaurant_id"),
    ("ck_reservations_restaurant_id_not_null", "reservations", "restaurant_id"),
]

_OWNER_PHONE_INDEX = "uq_restaurants_owner_phone"
_OWNER_PHONE_TABLE = "restaurants"
_OWNER_PHONE_COLUMN = "owner_phone"


def _existing_check_names(inspector, table: str) -> set[str]:
    try:
        return {c["name"] for c in inspector.get_check_constraints(table) if c.get("name")}
    except NotImplementedError:
        return set()


def _existing_index_names(inspector, table: str) -> set[str]:
    try:
        return {i["name"] for i in inspector.get_indexes(table) if i.get("name")}
    except NotImplementedError:
        return set()


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite/others: create_all already carries these (models.py). No-op.
        return

    inspector = sa.inspect(bind)

    for name, table, col in _NOT_NULL_CHECKS:
        if not inspector.has_table(table):
            continue
        if name in _existing_check_names(inspector, table):
            continue
        null_count = bind.execute(
            sa.text(f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL")
        ).scalar()
        if null_count and null_count > 0:
            logger.error(
                "[025] Skipping NOT NULL check on %s.%s: %d row(s) with NULL. "
                "This is a PERMANENT skip once this revision is stamped applied — "
                "run execution_checks/preflight_025.py, reconcile the rows, then "
                "add a follow-up migration to enforce it.",
                table, col, null_count,
            )
            continue
        # NOT VALID → applies to new/updated rows only; never scans/legacy-fails the deploy.
        op.execute(
            f'ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({col} IS NOT NULL) NOT VALID'
        )

    # Partial UNIQUE on owner_phone — guard against existing duplicates so we
    # never abort boot. WHERE owner_phone IS NOT NULL: it stays a legitimate,
    # optional field (restaurants that haven't set up WhatsApp yet).
    if inspector.has_table(_OWNER_PHONE_TABLE) and _OWNER_PHONE_INDEX not in _existing_index_names(inspector, _OWNER_PHONE_TABLE):
        dupes = bind.execute(sa.text(
            f"SELECT COUNT(*) FROM ("
            f"  SELECT {_OWNER_PHONE_COLUMN} FROM {_OWNER_PHONE_TABLE} "
            f"  WHERE {_OWNER_PHONE_COLUMN} IS NOT NULL "
            f"  GROUP BY {_OWNER_PHONE_COLUMN} HAVING COUNT(*) > 1"
            f") d"
        )).scalar()
        if dupes and dupes > 0:
            logger.error(
                "[025] Skipping unique index %s: %d duplicate owner_phone group(s) "
                "exist. PERMANENT skip once this revision is stamped applied — "
                "run execution_checks/preflight_025.py, reconcile duplicates, then "
                "add a follow-up migration to enforce it.",
                _OWNER_PHONE_INDEX, dupes,
            )
        else:
            op.execute(
                f'CREATE UNIQUE INDEX {_OWNER_PHONE_INDEX} ON {_OWNER_PHONE_TABLE} '
                f'({_OWNER_PHONE_COLUMN}) WHERE {_OWNER_PHONE_COLUMN} IS NOT NULL'
            )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)

    if _OWNER_PHONE_INDEX in _existing_index_names(inspector, _OWNER_PHONE_TABLE):
        op.execute(f'DROP INDEX {_OWNER_PHONE_INDEX}')

    for name, table, _col in _NOT_NULL_CHECKS:
        if name in _existing_check_names(inspector, table):
            op.drop_constraint(name, table, type_="check")
