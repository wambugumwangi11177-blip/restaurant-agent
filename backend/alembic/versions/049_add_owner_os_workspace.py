"""Persist private owner OS conversations and one display preference."""
from alembic import op
import sqlalchemy as sa

revision = "049_owner_os_workspace"
down_revision = "048_scope_attention_decisions"
branch_labels = None
depends_on = None


def _exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if not _exists("owner_os_conversations"):
        op.create_table(
            "owner_os_conversations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(length=120), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_owner_os_conversations_restaurant_id", "owner_os_conversations", ["restaurant_id"])
        op.create_index("ix_owner_os_conversations_owner_user_id", "owner_os_conversations", ["owner_user_id"])
        op.create_index("ix_owner_os_conversation_owner_updated", "owner_os_conversations", ["owner_user_id", "updated_at"])

    if not _exists("owner_os_messages"):
        op.create_table(
            "owner_os_messages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("owner_os_conversations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("role", sa.String(length=16), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("answer_type", sa.String(length=32), nullable=True),
            sa.Column("client_message_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("conversation_id", "client_message_id", name="uq_owner_os_client_message"),
        )
        op.create_index("ix_owner_os_messages_conversation_id", "owner_os_messages", ["conversation_id"])

    if not _exists("owner_os_preferences"):
        op.create_table(
            "owner_os_preferences",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("default_area", sa.String(length=48), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("restaurant_id", "owner_user_id", name="uq_owner_os_preference_scope"),
        )


def downgrade():
    for table in ("owner_os_preferences", "owner_os_messages", "owner_os_conversations"):
        if _exists(table):
            op.drop_table(table)
