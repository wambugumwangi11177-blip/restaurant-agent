"""integration mirror + provenance tables (workstream C, tasks C-1.2..C-1.5)

Revision ID: 046_add_integration_mirror_tables
Revises: 045_add_user_pin_lockout_columns
Create Date: 2026-09-11 00:00:00.000000

Run with: alembic upgrade head

Creates the four integration-mirror tables that mirror backend/integration/models.py:
source_systems, sync_cursors, mirror_events (append-only), reconcile_runs.
Design rule: mirrored rows are immutable and carry provenance
(source_system_id, source_id, source_version); corrections arrive as new
versions, never in-place UPDATEs. Idempotent via inspector checks, coexists
with a create_all()-seeded schema (same style as 041).
"""

from alembic import op
import sqlalchemy as sa

revision = "046_add_integration_mirror_tables"
down_revision = "045_add_user_pin_lockout_columns"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    insp = _insp()

    if "source_systems" not in insp.get_table_names():
        op.create_table(
            "source_systems",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("slug", sa.String(length=64), nullable=False),
            sa.Column("display_name", sa.String(length=200), nullable=False),
            sa.Column("mechanism", sa.String(length=32), nullable=False),
            sa.Column("is_authoritative", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("slug", name="uq_source_systems_slug"),
        )

    if "sync_cursors" not in insp.get_table_names():
        op.create_table(
            "sync_cursors",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_system_id", sa.Integer(), nullable=False),
            sa.Column("entity", sa.String(length=64), nullable=False),
            sa.Column("last_seen_version", sa.String(length=128), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("source_system_id", "entity", name="uq_sync_cursor_system_entity"),
        )
        op.create_index("ix_sync_cursor_system_entity", "sync_cursors", ["source_system_id", "entity"])

    if "mirror_events" not in insp.get_table_names():
        op.create_table(
            "mirror_events",
            sa.Column("id", sa.BigInteger(), primary_key=True),
            sa.Column("source_system_id", sa.Integer(), nullable=False),
            sa.Column("entity", sa.String(length=64), nullable=False),
            sa.Column("source_id", sa.String(length=128), nullable=False),
            sa.Column("source_version", sa.String(length=128), nullable=True),
            sa.Column("payload_sha256", sa.String(length=64), nullable=False),
            sa.Column("action", sa.String(length=32), nullable=False),
            sa.Column("reason", sa.String(length=256), nullable=True),
            sa.Column("received_at", sa.DateTime(), nullable=False),
            sa.Column("raw", sa.JSON(), nullable=True),
        )
        op.create_index(
            "ix_mirror_events_system_entity_received",
            "mirror_events",
            ["source_system_id", "entity", "received_at"],
        )
        op.create_index("ix_mirror_events_source_id", "mirror_events", ["source_id"])

    if "reconcile_runs" not in insp.get_table_names():
        op.create_table(
            "reconcile_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_system_id", sa.Integer(), nullable=False),
            sa.Column("entity", sa.String(length=64), nullable=False),
            sa.Column("source_count", sa.Integer(), nullable=False),
            sa.Column("mirror_count", sa.Integer(), nullable=False),
            sa.Column("source_checksum", sa.String(length=64), nullable=False),
            sa.Column("mirror_checksum", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("detail", sa.JSON(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    insp = _insp()
    for table in ("reconcile_runs", "mirror_events", "sync_cursors", "source_systems"):
        if table in insp.get_table_names():
            op.drop_table(table)
