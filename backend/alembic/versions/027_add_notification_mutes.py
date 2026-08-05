"""add per-user notification category mutes

Revision ID: 027_add_notification_mutes
Revises: 026_add_notification_audience
Create Date: 2026-08-05 00:00:00.000000

Run with: alembic upgrade head

The feed now records routine activity (every order, status change, payment), so
it needs a volume control. A row here means one user has muted one category.
Idempotent and dialect-aware, matching migrations 015-026; coexists with
create_all().
"""

from alembic import op
import sqlalchemy as sa

revision = "027_add_notification_mutes"
down_revision = "026_add_notification_audience"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return name in _insp().get_table_names()


def _index_exists(table: str, name: str) -> bool:
    return name in [i["name"] for i in _insp().get_indexes(table)]


def _constraint_exists(table: str, name: str) -> bool:
    try:
        return name in [c["name"] for c in _insp().get_unique_constraints(table)]
    except NotImplementedError:      # some dialects don't reflect these
        return False


def upgrade():
    if not _table_exists("notification_mutes"):
        op.create_table(
            "notification_mutes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("category", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            # Muting an already-muted category must be a no-op rather than a
            # second row that then takes two deletes to undo.
            sa.UniqueConstraint("user_id", "category",
                                name="uq_notification_mute_user_category"),
        )

    if _table_exists("notification_mutes"):
        # Every read is "which categories has THIS user muted", on every feed
        # poll — without the index that is a full scan of a table that grows
        # with users x categories.
        if not _index_exists("notification_mutes", "ix_notification_mutes_user_id"):
            op.create_index("ix_notification_mutes_user_id", "notification_mutes", ["user_id"])

        # A database created by create_all() before this migration existed would
        # already have the table but may predate the constraint.
        if not _constraint_exists("notification_mutes", "uq_notification_mute_user_category"):
            try:
                with op.batch_alter_table("notification_mutes") as batch:
                    batch.create_unique_constraint(
                        "uq_notification_mute_user_category", ["user_id", "category"])
            except Exception:
                # Best effort: the application-level guard in
                # notifications.set_mutes() also prevents duplicates, so a
                # dialect that cannot add the constraint in place must not block
                # the whole migration chain.
                pass


def downgrade():
    if _table_exists("notification_mutes"):
        op.drop_table("notification_mutes")
