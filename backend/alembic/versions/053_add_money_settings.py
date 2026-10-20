"""Two owner settings the money layer reads: how far above usual a cost must be to be flagged, and the cash kept aside for bills.

docs/v2/SPEC.md §4 sprint S3.3 (expense spike "≥ 25% (setting)"; the bill radar's opening position). Additive only: two
columns on `restaurant_settings` with server defaults, so a row written before this migration reads as the defaults.

The backend Dockerfile runs create_all() before `alembic upgrade head`; create_all never adds a column to a table that already
exists, so this migration is what does, and it skips a column that is already there (a fresh database made by create_all with
the current models). Offline (`--sql`) there is no connection to inspect, so upgrade renders the ADD COLUMNs and downgrade the DROPs.
"""
from alembic import op
import sqlalchemy as sa

revision = "053_money_settings"
down_revision = "052_money_ledger"
branch_labels = None
depends_on = None

COLUMNS = (
    ("expense_spike_pct", sa.Float(), "25"),
    ("bill_reserve_cents", sa.Integer(), "0"),
)


def _has_column(table: str, column: str, *, offline: bool) -> bool:
    if op.get_context().as_sql:
        return offline
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    for name, type_, default in COLUMNS:
        if not _has_column("restaurant_settings", name, offline=False):
            op.add_column("restaurant_settings", sa.Column(name, type_, nullable=False, server_default=default))


def downgrade():
    for name, _type, _default in reversed(COLUMNS):
        if _has_column("restaurant_settings", name, offline=True):
            with op.batch_alter_table("restaurant_settings") as batch:
                batch.drop_column(name)
