"""Join the storekeeper chain with the POS durable inbox.

Either parent can land first. This file is the single head once both
j03_store_control and 051_pos_durable_inbox are present.

Revision ID: j04_merge_store_pos
Revises: j03_store_control, 051_pos_durable_inbox
"""

revision = "j04_merge_store_pos"
down_revision = ("j03_store_control", "051_pos_durable_inbox")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
