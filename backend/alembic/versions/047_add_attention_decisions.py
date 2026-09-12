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
    op.create_table(
        "attention_decisions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("tenant_id", sa.Integer(),
                  sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("card_key", sa.String(), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("attention_decisions")