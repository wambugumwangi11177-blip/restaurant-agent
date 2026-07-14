"""add workflow engine tables (Phase 8)

Revision ID: 023_add_workflow_engine
Revises: 022_add_subscriptions
Create Date: 2026-07-12 00:00:00.000000

Run with: alembic upgrade head

Creates workflow_runs + workflow_steps for durable, multi-step agentic
processes. Idempotent via an inspector table check; coexists with create_all().
"""

from alembic import op
import sqlalchemy as sa

revision = "023_add_workflow_engine"
down_revision = "022_add_subscriptions"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if not _table_exists("workflow_runs"):
        op.create_table(
            "workflow_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("template", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="running"),
            sa.Column("context_json", sa.Text(), server_default="{}"),
            sa.Column("current_step", sa.Integer(), server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_workflow_runs_restaurant_status", "workflow_runs",
                        ["restaurant_id", "status"])

    if not _table_exists("workflow_steps"):
        op.create_table(
            "workflow_steps",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("workflow_runs.id"), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("step_type", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("output_json", sa.Text(), server_default="{}"),
            sa.Column("error", sa.Text(), server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_workflow_steps_run_seq", "workflow_steps", ["run_id", "seq"])


def downgrade():
    if _table_exists("workflow_steps"):
        op.drop_table("workflow_steps")
    if _table_exists("workflow_runs"):
        op.drop_table("workflow_runs")
