"""Scope owner acknowledgements and expire snoozes; preserve legacy audit rows."""
from alembic import op
import sqlalchemy as sa

revision = "048_scope_attention_decisions"
down_revision = "047_attention_decisions"
branch_labels = None
depends_on = None


def upgrade():
    # Fresh installs call create_all before Alembic. Do not duplicate columns.
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("attention_decisions")}
    with op.batch_alter_table("attention_decisions") as batch:
        if "restaurant_id" not in columns:
            batch.add_column(sa.Column("restaurant_id", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_attention_restaurant", "restaurants", ["restaurant_id"], ["id"])
        if "expires_at" not in columns:
            batch.add_column(sa.Column("expires_at", sa.DateTime(), nullable=True))
    indexes = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("attention_decisions")}
    if "ix_attention_decisions_restaurant_id" not in indexes:
        op.create_index("ix_attention_decisions_restaurant_id", "attention_decisions", ["restaurant_id"])
    # No safe restaurant can be inferred for old tenant-wide rows. Keep NULL;
    # the owner reviews resurfaced advice once, without cross-branch suppression.


def downgrade():
    op.drop_index("ix_attention_decisions_restaurant_id", table_name="attention_decisions")
    with op.batch_alter_table("attention_decisions") as batch:
        batch.drop_column("expires_at")
        batch.drop_column("restaurant_id")
