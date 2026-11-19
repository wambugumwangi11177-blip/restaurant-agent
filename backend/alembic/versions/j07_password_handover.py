"""Handover sign-in reset: password_reset_required and handover codes.

Revision ID: j07_password_handover
Revises: j06_store_photos_bills
"""
import sqlalchemy as sa
from alembic import op

revision = "j07_password_handover"
down_revision = "j06_store_photos_bills"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "users" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("users")}
    if "password_reset_required" not in existing:
        op.add_column(
            "users",
            sa.Column("password_reset_required", sa.Boolean(), nullable=False, server_default="0"),
        )
    if "handover_code_hash" not in existing:
        op.add_column("users", sa.Column("handover_code_hash", sa.String(), nullable=True))
    if "handover_code_expires_at" not in existing:
        op.add_column("users", sa.Column("handover_code_expires_at", sa.DateTime(), nullable=True))
    if "handover_failed_attempts" not in existing:
        op.add_column(
            "users",
            sa.Column("handover_failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        )
    if "handover_locked_until" not in existing:
        op.add_column("users", sa.Column("handover_locked_until", sa.DateTime(), nullable=True))


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "users" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("users")}
    for col in (
        "handover_locked_until",
        "handover_failed_attempts",
        "handover_code_expires_at",
        "handover_code_hash",
        "password_reset_required",
    ):
        if col in existing:
            op.drop_column("users", col)