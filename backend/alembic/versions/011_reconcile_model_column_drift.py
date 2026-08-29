"""reconcile columns that exist in models.py but not on a pre-existing table

Revision ID: 011_reconcile_model_column_drift
Revises: 010_add_inventory_last_alerted_at
Create Date: 2026-07-08 00:00:00.000000

Run with: alembic upgrade head

WHY THIS EXISTS
───────────────
This project's core schema has never been under migration control. `Dockerfile`'s
CMD runs `init_db()` (`Base.metadata.create_all`) and *then* `alembic upgrade head`.
`create_all` creates missing **tables**; it does not add missing **columns** to a
table that already exists. Alembic migrations 001-010 only ever add the columns
they were written for.

So any column added to `models.py` on an *existing* table, without a matching
migration, is present on every fresh database (create_all makes it) and absent on
every long-lived one (nothing ever adds it). Locally and in CI the tests build a
fresh SQLite file, so the drift is invisible; in production it is an
`UndefinedColumn` error the first time that attribute is selected.

Measured 2026-07-08: 164 of the model's columns have no `add_column` in any
migration. Most are original-schema columns that create_all wrote when the table
was first made, so they are fine. The audit flagged five as suspect —
`MenuItem.cost_price`, `MenuItem.prep_station`, `Reservation.customer_email`,
`Reservation.duration_minutes`, `Order.delivery_channel`. Four of those five
genuinely have no migration (`duration_minutes` is handled by 009). But deciding
*which* of the 164 are actually missing on the live database requires reading the
live database, and we will not introspect production on a hunch.

WHAT IT DOES INSTEAD
────────────────────
Reconciles rather than guesses. It asks the database it is being run against
which columns each table actually has, compares that to `models.py`, and adds
whatever is missing. On a fresh DB every column already exists and this is a
no-op; on a drifted prod DB it adds exactly the columns that drifted, and nothing
else. It is therefore safe and idempotent to run anywhere, including repeatedly,
which is what makes it correct without a prod introspection first.

SAFETY RULES
────────────
  • Only tables that already exist are touched. A missing table is create_all's
    job (and it runs first) — adding one here would duplicate that definition.
  • A NOT NULL column with no server default cannot be added to a table that has
    rows. Those are SKIPPED and printed loudly rather than crashing the deploy.
    Adding one needs a real data-backfill migration written by hand.
  • Postgres enum types are created (checkfirst) before the column that uses
    them, since `op.add_column` will not do it and errors with "type does not
    exist". No-op on SQLite.
  • Never drops or alters. `downgrade()` is deliberately a no-op — we cannot know
    which of these columns this migration added versus which create_all did, and
    dropping the wrong one destroys data.
"""

from alembic import op
import sqlalchemy as sa

revision = "011_reconcile_model_column_drift"
down_revision = "010_add_inventory_last_alerted_at"
branch_labels = None
depends_on = None


def _models_metadata():
    """models.py's metadata, imported lazily so alembic can load this file standalone."""
    import models
    return models.Base.metadata


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    added, skipped = [], []

    for table in _models_metadata().sorted_tables:
        if table.name not in existing_tables:
            # create_all owns table creation and runs before this migration.
            continue

        live_columns = {c["name"] for c in inspector.get_columns(table.name)}

        for col in table.columns:
            if col.name in live_columns:
                continue

            addable = col.nullable or col.server_default is not None
            if not addable:
                skipped.append(f"{table.name}.{col.name} (NOT NULL, no server_default)")
                continue

            # Copy the type so we don't mutate or re-attach the shared type object
            # from the model metadata. Stateful types (e.g. Enum) can break if the
            # same instance is used in two Column definitions.
            col_type = col.type.copy() if hasattr(col.type, "copy") else col.type

            # Postgres: the enum TYPE must exist before a column can reference it.
            # checkfirst avoids a duplicate-type error when another column already
            # created it. Harmless no-op on SQLite.
            if isinstance(col_type, sa.Enum):
                col_type.create(bind, checkfirst=True)

            # Extract the server_default argument in a form safe to pass to a new
            # Column. A ColumnDefault wraps a clause/scalar; FetchedValue is used
            # as-is. Passing the raw object from the source column works in
            # SQLAlchemy but can carry references back to the original column, so
            # we extract just the arg when it is a simple DefaultClause.
            server_default = col.server_default
            if isinstance(server_default, sa.schema.DefaultClause):
                server_default = server_default.arg

            op.add_column(
                table.name,
                sa.Column(
                    col.name,
                    col_type,
                    nullable=col.nullable,
                    server_default=server_default,
                ),
            )
            added.append(f"{table.name}.{col.name}")

    if added:
        print(f"[011] Added {len(added)} drifted column(s): {', '.join(added)}")
    else:
        print("[011] No column drift — models.py and the database already agree.")

    if skipped:
        print(
            "[011] WARNING: could not add "
            + f"{len(skipped)} NOT NULL column(s) with no server default: "
            + ", ".join(skipped)
            + ". These need a hand-written backfill migration."
        )


def downgrade() -> None:
    """
    Intentionally a no-op. This migration adds only the columns that were already
    missing, and it cannot know afterwards which of a table's columns it added
    versus which `create_all` created. Dropping on the basis of a guess would
    destroy data. Roll forward, not back.
    """
    pass