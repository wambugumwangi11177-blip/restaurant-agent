"""Owner settings: one row of typed thresholds per restaurant + an audit trail of every change.

docs/v2/SPEC.md §3.2 / sprint S1.1. Additive only: two new tables, no change to existing ones.

The backend Dockerfile runs create_all() before `alembic upgrade head`, so on a deploy the tables may
already exist with their indexes — same guard as 049/050. Offline (`--sql`) there is no connection to
inspect, so the guard is skipped and the real PostgreSQL DDL (up and down) is rendered for review.
"""
from alembic import op
import sqlalchemy as sa

revision = "051_restaurant_settings"
down_revision = "050_creative_takes"
branch_labels = None
depends_on = None


def _exists(name: str, *, offline: bool) -> bool:
    """Does the table exist? Offline (`--sql`) there is no connection to ask, so the caller says what to
    assume: upgrade assumes absent (render the CREATE), downgrade assumes present (render the DROP)."""
    if op.get_context().as_sql:
        return offline
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if not _exists("restaurant_settings", offline=False):
        op.create_table(
            "restaurant_settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("food_cost_target_pct", sa.Float(), nullable=False),
            sa.Column("prime_cost_target_pct", sa.Float(), nullable=False),
            sa.Column("margin_floor_pct", sa.Float(), nullable=False),
            sa.Column("margin_target_pct", sa.Float(), nullable=False),
            sa.Column("popular_cutoff", sa.Float(), nullable=False),
            sa.Column("missing_stock_flag_pct", sa.Float(), nullable=False),
            sa.Column("cash_tolerance_cents", sa.Integer(), nullable=False),
            sa.Column("cash_tolerance_pct", sa.Float(), nullable=False),
            sa.Column("commission_uber_eats_pct", sa.Float(), nullable=False),
            sa.Column("commission_glovo_pct", sa.Float(), nullable=False),
            sa.Column("commission_bolt_food_pct", sa.Float(), nullable=False),
            sa.Column("offer_size_pct", sa.Float(), nullable=False),
            sa.Column("offer_lift_pct", sa.Float(), nullable=False),
            sa.Column("max_raise_pct", sa.Float(), nullable=False),
            sa.Column("price_step_cents", sa.Integer(), nullable=False),
            sa.Column("price_sensitivity", sa.Float(), nullable=False),
            sa.Column("labour_target_pct", sa.Float(), nullable=False),
            sa.Column("overtime_after_hours", sa.Float(), nullable=False),
            sa.Column("urgent_alerts_per_day", sa.Integer(), nullable=False),
            sa.Column("quiet_hours_start", sa.Integer(), nullable=False),
            sa.Column("quiet_hours_end", sa.Integer(), nullable=False),
            sa.Column("licence_warning_days", sa.Integer(), nullable=False),
            sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("restaurant_id", name="uq_restaurant_settings_restaurant"),
        )
        op.create_index("ix_restaurant_settings_id", "restaurant_settings", ["id"])

    if not _exists("restaurant_settings_audit", offline=False):
        op.create_table(
            "restaurant_settings_audit",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("field", sa.String(length=48), nullable=False),
            sa.Column("old_value", sa.String(length=32), nullable=True),
            sa.Column("new_value", sa.String(length=32), nullable=False),
            sa.Column("changed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("changed_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_restaurant_settings_audit_id", "restaurant_settings_audit", ["id"])
        op.create_index("ix_restaurant_settings_audit_lookup", "restaurant_settings_audit", ["restaurant_id", "changed_at"])


def downgrade():
    if _exists("restaurant_settings_audit", offline=True):
        op.drop_table("restaurant_settings_audit")
    if _exists("restaurant_settings", offline=True):
        op.drop_table("restaurant_settings")
