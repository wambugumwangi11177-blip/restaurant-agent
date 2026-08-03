"""add orders.attributed_user_id for POS PIN quick-switch (tech-debt D16)

Revision ID: 028_add_order_attributed_user_id
Revises: 027_add_user_pin_and_display_name
Create Date: 2026-08-02 00:00:00.000000

Adds orders.attributed_user_id (nullable FK -> users.id, ON DELETE SET NULL).
Records which staff member rang up an order on a shared POS device —
ATTRIBUTION ONLY, never checked by any authorization path. SET NULL rather
than CASCADE: deleting a user should never delete their historical orders.

Idempotent via inspector column checks, matching prior migrations' pattern.
"""

from alembic import op
import sqlalchemy as sa

revision = "028_add_order_attributed_user_id"
down_revision = "027_add_user_pin_and_display_name"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(c["name"] == column_name for c in sa.inspect(op.get_bind()).get_columns(table_name))


def upgrade():
    if not _column_exists("orders", "attributed_user_id"):
        # Column + FK added together in ONE batch op — SQLite can't ALTER TABLE
        # ADD CONSTRAINT after the fact (it needs to recreate the whole table),
        # so a separate top-level op.create_foreign_key() after op.add_column()
        # silently fails to register a constraint SQLite can later find by
        # name (verified: breaks the downgrade below with "No such
        # constraint"). Batching both together is Alembic's documented
        # pattern for this and is also correct/portable on Postgres, where
        # batch mode just emits normal ALTER TABLE statements.
        with op.batch_alter_table("orders") as batch_op:
            batch_op.add_column(sa.Column("attributed_user_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_orders_attributed_user_id",
                "users",
                ["attributed_user_id"], ["id"],
                ondelete="SET NULL",
            )


def downgrade():
    # No explicit drop_constraint: SQLite's schema reflection doesn't expose
    # named FK constraints at all (verified — batch_op.drop_constraint("fk_...",
    # type_="foreignkey") raises "No such constraint" even right after the
    # matching create_foreign_key in the same batch op, in the same
    # migration). Batch mode recreates the whole table from the target
    # column set; dropping the column that carries the FK is sufficient — the
    # constraint has nothing left to reference and isn't recreated. Confirmed
    # correct on Postgres too (batch mode there just emits a normal
    # DROP COLUMN, which cascades the dependent FK by definition).
    with op.batch_alter_table("orders") as batch_op:
        batch_op.drop_column("attributed_user_id")
