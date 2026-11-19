"""PIN app-lock: track last full password authentication

Revision ID: j08_password_auth_at
Revises: j07_password_handover
Create Date: 2026-11-19

"""
from alembic import op
import sqlalchemy as sa

revision = "j08_password_auth_at"
down_revision = "j07_password_handover"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("password_authenticated_at", sa.DateTime(), nullable=True),
    )
    op.execute(
        "UPDATE users SET password_authenticated_at = last_login_at "
        "WHERE last_login_at IS NOT NULL AND password_authenticated_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("users", "password_authenticated_at")