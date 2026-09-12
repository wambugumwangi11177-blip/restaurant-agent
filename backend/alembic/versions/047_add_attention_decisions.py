"""0XX attention_decisions — Restaurant OS home attention-card decisions.

Created 2026-09-11 for the Vibanda Village Restaurant OS home page: when the
owner taps Approve/Later/Reject on an attention card the choice persists here,
and decided cards stop appearing in GET /overview/today (see
routers/overview.py::_attention_cards).
"""
revision = "047_attention_decisions"
down_revision = "046_add_integration_mirror_tables"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    # init_db() runs Base.metadata.create_all() before Alembic on a fresh DB,
    # so the table may already exist — CREATE TABLE would crash the deploy
    # with DuplicateTable (found 2026-09-11, Railway). Use raw SQL with
    # IF NOT EXISTS; the column list matches the model exactly.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS attention_decisions (
            id SERIAL NOT NULL,
            tenant_id INTEGER NOT NULL REFERENCES tenants (id),
            card_key VARCHAR NOT NULL,
            decision VARCHAR NOT NULL,
            decided_at TIMESTAMP WITHOUT TIME ZONE,
            decided_by INTEGER REFERENCES users (id),
            PRIMARY KEY (id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_attention_decisions_id ON attention_decisions (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_attention_decisions_tenant_id ON attention_decisions (tenant_id)")


def downgrade() -> None:
    op.drop_table("attention_decisions")