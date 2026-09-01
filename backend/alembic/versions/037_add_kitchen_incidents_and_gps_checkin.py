"""kitchen incidents (remakes/quality issues) + GPS staff check-in

Revision ID: 037_add_kitchen_incidents_and_gps_checkin
Revises: 036_add_missing_fk_indexes
Create Date: 2026-07-19 00:00:00.000000

Run with: alembic upgrade head

Two independent additions from the same planning pass (owner's operational
walkthrough notes):

  1. kitchen_incidents: previously nowhere to record a remake or a kitchen
     quality issue at all — see models.py's KitchenIncident docstring.
  2. GPS check-in: labor_shifts gains clock_in/out lat+lng (nullable, opt-in)
     and a clock_in_flagged boolean; restaurants gains latitude/longitude
     (nullable — a proximity check is only ever run once an owner has set
     these, never guessed at).

Idempotent via inspector checks, coexists with a create_all()-seeded schema.
"""

from alembic import op
import sqlalchemy as sa

revision = "037_add_kitchen_incidents_and_gps_checkin"
down_revision = "036_add_missing_fk_indexes"
branch_labels = None
depends_on = None

INCIDENT_TYPE_VALUES = ("REMAKE", "QUALITY_ISSUE", "OTHER")


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _insp().get_table_names()


def _column_exists(table: str, column: str) -> bool:
    if not _table_exists(table):
        return False
    return column in [c["name"] for c in _insp().get_columns(table)]


def upgrade():
    if not _table_exists("kitchen_incidents"):
        # No separate .create(checkfirst=True) call — op.create_table's own
        # enum-creation-on-table-create does not respect checkfirst against
        # real Postgres (see 025/032's writeup of this SQLAlchemy behavior).
        incident_type_enum = sa.Enum(*INCIDENT_TYPE_VALUES, name="incidenttype")
        op.create_table(
            "kitchen_incidents",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
            sa.Column("order_item_id", sa.Integer(), sa.ForeignKey("order_items.id"), nullable=True),
            sa.Column("incident_type", incident_type_enum, nullable=False),
            sa.Column("reason", sa.Text(), server_default=""),
            sa.Column("reported_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_kitchen_incidents_restaurant_created", "kitchen_incidents",
                         ["restaurant_id", "created_at"])

    if not _column_exists("restaurants", "latitude"):
        op.add_column("restaurants", sa.Column("latitude", sa.Float(), nullable=True))
    if not _column_exists("restaurants", "longitude"):
        op.add_column("restaurants", sa.Column("longitude", sa.Float(), nullable=True))

    if _column_exists("labor_shifts", "actual_start"):
        if not _column_exists("labor_shifts", "clock_in_lat"):
            op.add_column("labor_shifts", sa.Column("clock_in_lat", sa.Float(), nullable=True))
        if not _column_exists("labor_shifts", "clock_in_lng"):
            op.add_column("labor_shifts", sa.Column("clock_in_lng", sa.Float(), nullable=True))
        if not _column_exists("labor_shifts", "clock_out_lat"):
            op.add_column("labor_shifts", sa.Column("clock_out_lat", sa.Float(), nullable=True))
        if not _column_exists("labor_shifts", "clock_out_lng"):
            op.add_column("labor_shifts", sa.Column("clock_out_lng", sa.Float(), nullable=True))
        if not _column_exists("labor_shifts", "clock_in_flagged"):
            op.add_column("labor_shifts", sa.Column(
                "clock_in_flagged", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    if _column_exists("labor_shifts", "clock_in_flagged"):
        op.drop_column("labor_shifts", "clock_in_flagged")
    if _column_exists("labor_shifts", "clock_out_lng"):
        op.drop_column("labor_shifts", "clock_out_lng")
    if _column_exists("labor_shifts", "clock_out_lat"):
        op.drop_column("labor_shifts", "clock_out_lat")
    if _column_exists("labor_shifts", "clock_in_lng"):
        op.drop_column("labor_shifts", "clock_in_lng")
    if _column_exists("labor_shifts", "clock_in_lat"):
        op.drop_column("labor_shifts", "clock_in_lat")

    if _column_exists("restaurants", "longitude"):
        op.drop_column("restaurants", "longitude")
    if _column_exists("restaurants", "latitude"):
        op.drop_column("restaurants", "latitude")

    if _table_exists("kitchen_incidents"):
        op.drop_table("kitchen_incidents")
        sa.Enum(name="incidenttype").drop(op.get_bind(), checkfirst=True)
