"""Company OS Kernel: agent action proposals (audit trail) + per-tool earned autonomy."""
from alembic import op
import sqlalchemy as sa

revision = "051_company_os_kernel"
down_revision = "050_creative_takes"
branch_labels = None
depends_on = None


def _exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if not _exists("company_proposals"):
        op.create_table(
            "company_proposals",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("agent", sa.String(), nullable=False),
            sa.Column("tool", sa.String(), nullable=False),
            sa.Column("tier", sa.String(), nullable=False),
            sa.Column("summary", sa.String(), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id", ondelete="SET NULL"), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("auto_executed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("edited", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("decided_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("result", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("decided_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_company_proposals_id", "company_proposals", ["id"])
        op.create_index("ix_company_proposals_tool", "company_proposals", ["tool"])
        op.create_index("ix_company_proposals_status", "company_proposals", ["status"])
        op.create_index("ix_company_proposals_restaurant_id", "company_proposals", ["restaurant_id"])
    if not _exists("company_tool_autonomy"):
        op.create_table(
            "company_tool_autonomy",
            sa.Column("tool", sa.String(), primary_key=True),
            sa.Column("streak", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("autonomous", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )


def downgrade():
    for t in ("company_tool_autonomy", "company_proposals"):
        if _exists(t):
            op.drop_table(t)
