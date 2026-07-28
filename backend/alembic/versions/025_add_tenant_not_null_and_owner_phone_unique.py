"""add NOT NULL on operational restaurant_id columns + unique owner_phone

Revision ID: 025_add_tenant_not_null_and_owner_phone_unique
Revises: 024_add_enterprise_hierarchy
Create Date: 2026-07-27 00:00:00.000000

Run with: alembic upgrade head

Two real gaps found in a full-stack audit:

1. Five operational restaurant_id FK columns are nullable at the DB level even
   though every router relies on filtering by them (orders.restaurant_id,
   reservations.restaurant_id, menu_items.restaurant_id, tables.restaurant_id,
   inventory_items.restaurant_id). A NULL here — an app bug, a bad migration, a
   manual SQL edit — makes that row silently invisible to every tenant-scoped
   query instead of raising an error.

   Scope note: the audit also flagged restaurants.tenant_id and users.tenant_id
   as nullable. Deliberately NOT included here — `tenant_id=None` turned out to
   be a widespread, intentional shortcut used across ~28 existing test files
   (a standalone Restaurant/User with no real Tenant row, for tests that don't
   care about tenant isolation specifically). Enforcing NOT NULL there would
   break all of them and needs its own dedicated cleanup pass, not a rider on
   this migration. The 5 columns actually fixed here have zero such usage
   (confirmed: no test anywhere constructs an Order/Reservation/MenuItem/Table/
   InventoryItem with restaurant_id=None) — a materially different, safe case.
2. restaurants.owner_phone has no uniqueness constraint. Since the WhatsApp
   command router resolves the sender to a restaurant by this column, two
   restaurants sharing a phone number (accidental duplicate entry, not fixed
   here: a deliberate hijack, which needs an OTP verification flow — out of
   scope for a DB constraint) risks routing one tenant's commands/data to the
   other.

DEPLOY SAFETY, same standard as 016_add_integrity_constraints.py:

  • NOT NULL is added via the two-step online-safe idiom Postgres recommends
    (016's own NOT VALID trick is CHECK-only; Postgres has no NOT VALID for
    ALTER COLUMN ... SET NOT NULL):
      ADD CONSTRAINT ..._not_null CHECK (col IS NOT NULL) NOT VALID   -- instant, no scan
      VALIDATE CONSTRAINT ..._not_null                                -- online, doesn't block writes
      ALTER COLUMN col SET NOT NULL                                  -- now instant: the
                                                                          validated CHECK already
                                                                          proves no NULLs exist
    Each of the three sub-steps is skipped if already applied, so a partial
    prior run (e.g. a boot that died mid-migration) resumes cleanly.
  • Pre-flight guard: if any NULLs already exist in a column, that column is
    logged and SKIPPED entirely (no CHECK added, no attempt at NOT NULL) —
    exactly 016's "skip on violation, never fail the deploy" precedent.
  • owner_phone UNIQUE uses a plain guarded `op.create_unique_constraint`,
    NOT `CREATE INDEX CONCURRENTLY` — this repo's alembic/env.py wraps every
    migration in `context.begin_transaction()` (confirmed by reading it), and
    CONCURRENTLY cannot run inside a transaction block; attempting it would
    fail the deploy outright, the opposite of what this migration is for.
    016 already accepts the same plain-lock tradeoff for the (much larger)
    `tables` unique constraint; `restaurants` has one row per tenant, so the
    lock is momentary regardless. Partial index (WHERE owner_phone IS NOT
    NULL) so restaurants that haven't set up WhatsApp yet are unaffected.
  • On SQLite (tests/local): no-op, same as 016 — fresh SQLite DBs already
    carry `nullable=False`/unique from models.py via create_all() once
    models.py itself is updated to match (done in this same change).
"""

import logging

from alembic import op
import sqlalchemy as sa

revision = "025_add_tenant_not_null_and_owner_phone_unique"
down_revision = "024_add_enterprise_hierarchy"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.025")

# (table, column) — see module docstring for why restaurants.tenant_id and
# users.tenant_id are deliberately NOT in this list.
_NOT_NULL_COLUMNS = [
    ("orders", "restaurant_id"),
    ("reservations", "restaurant_id"),
    ("menu_items", "restaurant_id"),
    ("tables", "restaurant_id"),
    ("inventory_items", "restaurant_id"),
]

_OWNER_PHONE_UNIQUE = "uq_restaurants_owner_phone"


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


def _is_not_null_already(inspector, table: str, column: str) -> bool:
    for col in inspector.get_columns(table):
        if col["name"] == column:
            return not col.get("nullable", True)
    return False


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite/others: create_all already carries these (models.py, updated
        # alongside this migration). No-op, matching 016's precedent.
        return

    inspector = sa.inspect(bind)

    for table, column in _NOT_NULL_COLUMNS:
        if not inspector.has_table(table):
            continue
        if _is_not_null_already(inspector, table, column):
            continue

        null_count = bind.execute(sa.text(
            f"SELECT COUNT(*) FROM {table} WHERE {column} IS NULL"
        )).scalar()
        if null_count and null_count > 0:
            logger.warning(
                "[025] Skipping NOT NULL on %s.%s: %d existing NULL row(s). "
                "Backfill or reconcile, then re-run.",
                table, column, null_count,
            )
            continue

        check_name = f"ck_{table}_{column}_not_null"
        if check_name not in _existing_check_names(inspector, table):
            op.execute(
                f'ALTER TABLE {table} ADD CONSTRAINT {check_name} '
                f'CHECK ({column} IS NOT NULL) NOT VALID'
            )
        op.execute(f'ALTER TABLE {table} VALIDATE CONSTRAINT {check_name}')
        op.execute(f'ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL')
        # The CHECK's job was only to make SET NOT NULL scan-free; once the
        # column is genuinely NOT NULL the CHECK is redundant weight on every
        # future insert/update. Drop it now that its purpose is served.
        op.execute(f'ALTER TABLE {table} DROP CONSTRAINT {check_name}')

    # owner_phone uniqueness — see module docstring for why this is a plain
    # guarded constraint, not CREATE INDEX CONCURRENTLY.
    if inspector.has_table("restaurants") and _OWNER_PHONE_UNIQUE not in _existing_unique_names(inspector, "restaurants"):
        dupes = bind.execute(sa.text(
            "SELECT COUNT(*) FROM (SELECT owner_phone FROM restaurants "
            "WHERE owner_phone IS NOT NULL GROUP BY owner_phone HAVING COUNT(*) > 1) d"
        )).scalar()
        if dupes and dupes > 0:
            logger.warning(
                "[025] Skipping %s: %d duplicate owner_phone group(s) exist. "
                "Reconcile duplicates then re-run to enforce uniqueness.",
                _OWNER_PHONE_UNIQUE, dupes,
            )
        else:
            op.execute(
                f'ALTER TABLE restaurants ADD CONSTRAINT {_OWNER_PHONE_UNIQUE} '
                f'UNIQUE (owner_phone)'
            )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)

    if _OWNER_PHONE_UNIQUE in _existing_unique_names(inspector, "restaurants"):
        op.drop_constraint(_OWNER_PHONE_UNIQUE, "restaurants", type_="unique")

    for table, column in _NOT_NULL_COLUMNS:
        if not inspector.has_table(table):
            continue
        if _is_not_null_already(inspector, table, column):
            op.execute(f'ALTER TABLE {table} ALTER COLUMN {column} DROP NOT NULL')
