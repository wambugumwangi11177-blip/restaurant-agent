"""add enterprise hierarchy: organizations, regions, restaurant FKs (Phase 10)

Revision ID: 024_add_enterprise_hierarchy
Revises: 023_add_workflow_engine
Create Date: 2026-07-12 00:00:00.000000

Run with: alembic upgrade head

Creates organizations + regions and adds nullable organization_id / region_id to
restaurants. Nullable + idempotent: existing single-location restaurants are
untouched. Coexists with create_all().
"""

from alembic import op
import sqlalchemy as sa

revision = "024_add_enterprise_hierarchy"
down_revision = "023_add_workflow_engine"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _insp().get_table_names()


def _column_exists(table: str, column: str) -> bool:
    return column in [c["name"] for c in _insp().get_columns(table)]


def upgrade():
    if not _table_exists("organizations"):
        op.create_table(
            "organizations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_organizations_tenant_id", "organizations", ["tenant_id"])

    if not _table_exists("regions"):
        op.create_table(
            "regions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("manager_email", sa.String(), server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_regions_organization_id", "regions", ["organization_id"])

    if _table_exists("restaurants"):
        if not _column_exists("restaurants", "organization_id"):
            op.add_column("restaurants", sa.Column("organization_id", sa.Integer(), nullable=True))
            op.create_index("ix_restaurants_organization_id", "restaurants", ["organization_id"])
        if not _column_exists("restaurants", "region_id"):
            op.add_column("restaurants", sa.Column("region_id", sa.Integer(), nullable=True))
            op.create_index("ix_restaurants_region_id", "restaurants", ["region_id"])


def downgrade():
    # Column drops are intentionally skipped on SQLite (no-op there); the tables
    # can be dropped safely.
    if _table_exists("regions"):
        op.drop_table("regions")
    if _table_exists("organizations"):
        op.drop_table("organizations")
