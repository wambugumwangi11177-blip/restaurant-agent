"""One owner setting the M-Pesa check reads: how many minutes apart a sale and its payment may be.

docs/v2/SPEC.md §4 sprint S6.2 (matching "exact (amount, ±10 min)", the 10 being the owner's to change, §0.3). Additive only: one column on
`restaurant_settings` with a server default, so a row written before this migration reads as the default.

The backend Dockerfile runs create_all() before `alembic upgrade head`; create_all never adds a column to a table that already exists, so
this migration is what does, and it skips a column that is already there. Offline (`--sql`) there is no connection to inspect, so upgrade
renders the ADD COLUMN and downgrade the DROP.
"""
from alembic import op
import sqlalchemy as sa

revision = "056_mpesa_match_setting"
down_revision = "055_mpesa_statements"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str, *, offline: bool) -> bool:
    if op.get_context().as_sql:
        return offline
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    if not _has_column("restaurant_settings", "mpesa_match_minutes", offline=False):
        op.add_column("restaurant_settings", sa.Column("mpesa_match_minutes", sa.Integer(), nullable=False, server_default="10"))


def downgrade():
    if _has_column("restaurant_settings", "mpesa_match_minutes", offline=True):
        with op.batch_alter_table("restaurant_settings") as batch:
            batch.drop_column("mpesa_match_minutes")
