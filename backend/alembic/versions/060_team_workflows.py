"""Branch-scoped approval requests, delegated tasks and their audit events."""
from alembic import op
import sqlalchemy as sa

revision = "060_team_workflows"
down_revision = "059_scheduled_price_ondelete"
branch_labels = None
depends_on = None


def upgrade():
    # init_db may have created current tables before Alembic runs on first boot.
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("team_workflows"):
        op.create_table("team_workflows",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("assigned_to", sa.Integer(), sa.ForeignKey("users.id")),
            sa.Column("request_key", sa.String(160), unique=True, nullable=False),
            sa.Column("kind", sa.String(24), nullable=False),
            sa.Column("title", sa.String(160), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("due_on", sa.Date()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False))
        op.create_index("ix_team_workflows_restaurant_id", "team_workflows", ["restaurant_id"])
    if not sa.inspect(bind).has_table("team_workflow_events"):
        op.create_table("team_workflow_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("workflow_id", sa.Integer(), sa.ForeignKey("team_workflows.id"), nullable=False),
            sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("action", sa.String(24), nullable=False),
            sa.Column("note", sa.String(500), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False))
        op.create_index("ix_team_workflow_events_workflow_id", "team_workflow_events", ["workflow_id"])


def downgrade():
    op.drop_table("team_workflow_events")
    op.drop_table("team_workflows")
