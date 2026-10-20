"""A notification remembers why no push went out (alert levels).

docs/v2/SPEC.md §4 sprint S5.3 ("now: push, max per day, quiet hours"). Additive only: one nullable column on `notifications`, so
every row written before this migration reads as "pushed, or not under the owner policy" (NULL). A held alert is still a row in the
in-app feed; the column says why no push went with it ("quiet_hours" · "daily_cap" · "today"), and the evening digest lists them.

The backend Dockerfile runs create_all() before `alembic upgrade head`; create_all never adds a column to a table that already exists,
so this migration is what does, and it skips a column that is already there (a fresh database made by create_all with the current
models). Offline (`--sql`) there is no connection to inspect, so upgrade renders the ADD COLUMN and downgrade the DROP.
"""
from alembic import op
import sqlalchemy as sa

revision = "054_notification_push_held"
down_revision = "053_money_settings"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str, *, offline: bool) -> bool:
    if op.get_context().as_sql:
        return offline
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    if not _has_column("notifications", "push_held", offline=False):
        op.add_column("notifications", sa.Column("push_held", sa.String(), nullable=True))


def downgrade():
    if _has_column("notifications", "push_held", offline=True):
        with op.batch_alter_table("notifications") as batch:
            batch.drop_column("push_held")
