"""Team weekly shifts, overrides, rules, schedule approvals, reminders.

Revision ID: j10_team_schedule
Revises: j09_data_wall
"""
import sqlalchemy as sa
from alembic import op

revision = "j10_team_schedule"
down_revision = "j09_data_wall"
branch_labels = None
depends_on = None


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str):
    if table not in _tables():
        return set()
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "daily_pay_rate_cents" not in _columns("staff_members"):
        op.add_column(
            "staff_members",
            sa.Column("daily_pay_rate_cents", sa.Integer(), nullable=True),
        )

    if "staff_weekly_shifts" not in _tables():
        op.create_table(
            "staff_weekly_shifts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("restaurant_id", sa.Integer(), nullable=False),
            sa.Column("staff_member_id", sa.Integer(), nullable=False),
            sa.Column("weekday", sa.Integer(), nullable=False),
            sa.Column("start_time", sa.String(), nullable=False),
            sa.Column("end_time", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["staff_member_id"], ["staff_members.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("staff_member_id", "weekday", name="uq_staff_weekly_member_day"),
        )
        op.create_index("ix_staff_weekly_shifts_restaurant", "staff_weekly_shifts", ["restaurant_id"])

    if "staff_shift_overrides" not in _tables():
        op.create_table(
            "staff_shift_overrides",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("restaurant_id", sa.Integer(), nullable=False),
            sa.Column("staff_member_id", sa.Integer(), nullable=False),
            sa.Column("shift_date", sa.Date(), nullable=False),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("swap_staff_member_id", sa.Integer(), nullable=True),
            sa.Column("created_by_user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["staff_member_id"], ["staff_members.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["swap_staff_member_id"], ["staff_members.id"]),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_staff_shift_overrides_date", "staff_shift_overrides", ["restaurant_id", "shift_date"])

    if "team_rules" not in _tables():
        op.create_table(
            "team_rules",
            sa.Column("restaurant_id", sa.Integer(), nullable=False),
            sa.Column("alerts_enabled", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("max_hours_per_week", sa.Float(), nullable=False, server_default="52"),
            sa.Column("max_consecutive_days", sa.Integer(), nullable=False, server_default="6"),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("restaurant_id"),
        )

    if "schedule_change_requests" not in _tables():
        op.create_table(
            "schedule_change_requests",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("restaurant_id", sa.Integer(), nullable=False),
            sa.Column("proposed_by_user_id", sa.Integer(), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(), nullable=False, server_default="needs_approval"),
            sa.Column("owner_note", sa.Text(), server_default=""),
            sa.Column("decided_by_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("decided_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["proposed_by_user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if "approval_reminders" not in _tables():
        op.create_table(
            "approval_reminders",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("restaurant_id", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("entity_id", sa.Integer(), nullable=False),
            sa.Column("requester_user_id", sa.Integer(), nullable=True),
            sa.Column("actor_staff_role", sa.String(), nullable=False, server_default="owner"),
            sa.Column("stage", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_sent_at", sa.DateTime(), nullable=True),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["requester_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("restaurant_id", "kind", "entity_id", name="uq_approval_reminder_entity"),
        )


def downgrade() -> None:
    for table in (
        "approval_reminders",
        "schedule_change_requests",
        "team_rules",
        "staff_shift_overrides",
        "staff_weekly_shifts",
    ):
        if table in _tables():
            op.drop_table(table)
    if "daily_pay_rate_cents" in _columns("staff_members"):
        op.drop_column("staff_members", "daily_pay_rate_cents")