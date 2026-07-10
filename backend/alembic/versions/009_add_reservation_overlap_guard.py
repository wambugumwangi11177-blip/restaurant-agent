"""add DB-level overlap guard for table reservations

Revision ID: 009_add_reservation_overlap_guard
Revises: 008_add_optout_and_last_login
Create Date: 2026-07-08 00:00:00.000000

Run with: alembic upgrade head

Closes the concurrency gap that `ai/reservation_optimizer.find_available_tables`
has documented in its own docstring since Phase 2: availability was checked, then
the row was inserted, with nothing stopping a second writer from passing the same
check in between. (Auditing this on 2026-07-08 turned up something worse than the
race the docstring warned about — `routers/reservations.create_reservation` never
called the availability check *at all*, so two plain sequential requests could
double-book. That half is fixed in the router; this migration handles the half
the application layer genuinely cannot.)

Why EXCLUDE USING gist rather than the partial unique index that guards PENDING
pricing recommendations (001_add_agent_tables.py): uniqueness cannot express
interval overlap. Bookings on one table at 18:00 and 18:30 are distinct rows
under every possible unique key, yet they conflict. Range exclusion is the only
DB-level construct that states "no two rows whose time ranges intersect."

Postgres-only, and a deliberate no-op elsewhere. SQLite (local dev + the test
suite, per 001's docstring) has neither GiST nor exclusion constraints. The
application-level check in the router is therefore what the tests exercise; this
constraint is the production backstop that makes the check's TOCTOU window safe.

NOT YET EXECUTED AGAINST POSTGRES. No local Postgres exists in this environment,
and the only reachable instance is the production Neon database — running untested
DDL there to prove a migration works is not an acceptable way to test it. The DDL
is reviewed but unrun; the test suite exercises the router's check on SQLite and
asserts this migration is a clean no-op there. Run `alembic upgrade head` against
a staging/branch Postgres before deploying. Two specific things to confirm on
first real run: that `CREATE EXTENSION btree_gist` is permitted by the role, and
that the constraint builds against any *existing* reservation rows — if
production already contains overlapping CONFIRMED bookings (very possible, since
nothing has ever prevented them), ADD CONSTRAINT will fail until those rows are
reconciled. Query for them first:

    SELECT a.id, b.id, a.table_id, a.reservation_date
    FROM reservations a JOIN reservations b
      ON a.table_id = b.table_id AND a.id < b.id
     AND a.reservation_date = b.reservation_date
     AND a.status = 'CONFIRMED' AND b.status = 'CONFIRMED'
     AND tsrange(a.reservation_date + a.reservation_time,
                 a.reservation_date + a.reservation_time
                   + (coalesce(a.duration_minutes,90) * interval '1 minute'))
      && tsrange(b.reservation_date + b.reservation_time,
                 b.reservation_date + b.reservation_time
                   + (coalesce(b.duration_minutes,90) * interval '1 minute'));

Notes on the expression:
  • `reservation_date + reservation_time` yields a timestamp and is immutable, so
    it is indexable. Same for the interval arithmetic.
  • `coalesce(duration_minutes, 90)` mirrors the `or 90` default the Python side
    applies (models.Reservation.duration_minutes is nullable).
  • `tsrange(start, end)` is half-open '[)' by default — exactly the boundary
    semantics of `_intervals_overlap`, so a booking ending at 19:30 does not
    conflict with one starting at 19:30. The two layers agree by construction.
  • Scoped by table_id only, not (restaurant_id, table_id): a table belongs to
    exactly one restaurant, so table_id already implies the tenant. The WHERE
    clause skips CANCELLED/COMPLETED/NO_SHOW rows and unassigned (table_id NULL)
    reservations, matching the router's and the optimizer's filters.
  • `status = 'CONFIRMED'` uses the enum *name*, not the value ('confirmed').
    SQLAlchemy's Enum() persists names by default — the same convention
    001's `WHERE status = 'PENDING'` relies on.
"""

from alembic import op
import sqlalchemy as sa

revision = "009_add_reservation_overlap_guard"
down_revision = "008_add_optout_and_last_login"
branch_labels = None
depends_on = None

CONSTRAINT_NAME = "excl_reservation_table_no_overlap"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _constraint_exists(name: str) -> bool:
    return bool(
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM pg_constraint WHERE conname = :n"), {"n": name})
        .scalar()
    )


def upgrade() -> None:
    if not _is_postgres():
        return

    # btree_gist supplies the `=` operator class for the scalar table_id column;
    # without it GiST can only index the range, and the constraint won't build.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    if _constraint_exists(CONSTRAINT_NAME):
        return

    op.execute(
        f"""
        ALTER TABLE reservations
        ADD CONSTRAINT {CONSTRAINT_NAME}
        EXCLUDE USING gist (
            table_id WITH =,
            tsrange(
                reservation_date + reservation_time,
                reservation_date + reservation_time
                    + (coalesce(duration_minutes, 90) * interval '1 minute')
            ) WITH &&
        )
        WHERE (status = 'CONFIRMED' AND table_id IS NOT NULL)
        """
    )


def downgrade() -> None:
    if not _is_postgres():
        return
    op.execute(f"ALTER TABLE reservations DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME}")
