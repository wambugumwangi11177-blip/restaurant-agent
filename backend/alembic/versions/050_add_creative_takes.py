"""Persist creative LLM takes: the cache behind Home/OS/Reports text and an audit
trail of exactly what the AI told the owner (ADR 0007)."""
from alembic import op
import sqlalchemy as sa

revision = "050_creative_takes"
down_revision = "049_owner_os_workspace"
branch_labels = None
depends_on = None


def _exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    # The Dockerfile runs create_all() before `alembic upgrade head`, so on a
    # fresh deploy the table may already exist with its indexes — same guard as
    # 049. The indexes are only created together with the table.
    if not _exists("creative_takes"):
        op.create_table(
            "creative_takes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
            sa.Column("surface", sa.String(length=16), nullable=False),
            sa.Column("period", sa.String(length=16), nullable=False),
            sa.Column("mode", sa.String(length=24), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("evidence_hash", sa.String(length=64), nullable=False),
            sa.Column("llm_model", sa.String(length=128), nullable=True),
            sa.Column("prompt_version", sa.String(length=48), nullable=True),
            sa.Column("dropped_sentences", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_creative_takes_id", "creative_takes", ["id"])
        op.create_index(
            "ix_creative_takes_lookup", "creative_takes",
            ["restaurant_id", "surface", "period", "mode", "created_at"],
        )


def downgrade():
    if _exists("creative_takes"):
        op.drop_table("creative_takes")
