"""048 projection_links — mirror rows to domain rows.

Created 2026-09-19. The MacSoft mirror (migration 046) is append-only staging:
integration/ingest.py writes a MirrorEvent per record and stops there. Nothing
read those rows, so a successful push changed nothing the owner could see —
orders, menu_items and inventory_items are what every agent and the Home page
query, and the mirror is a different declarative base entirely.

integration/projection.py closes that gap. This table is the idempotency key
for it: one row per (source_system, entity, source_id), recording either the
domain row it became or why it could not be mapped. Re-projecting the same
mirror record updates the linked domain row instead of inserting a second one,
which is what makes reproject_all() safe to run every time the field mapping
improves — and it will improve, because MacSoft's real payload shape has still
not been seen.
"""
revision = "048_projection_links"
down_revision = "047_attention_decisions"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    # Same IF NOT EXISTS posture as 047: init_db() runs create_all() before
    # Alembic on a fresh database, so the table may already be there.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS projection_links (
            id SERIAL NOT NULL,
            source_system_id INTEGER NOT NULL,
            entity VARCHAR(64) NOT NULL,
            source_id VARCHAR(256) NOT NULL,
            status VARCHAR(16) NOT NULL,
            domain_table VARCHAR(64),
            domain_id INTEGER,
            projected_version VARCHAR(128),
            reason VARCHAR(256),
            projected_at TIMESTAMP WITHOUT TIME ZONE,
            PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_projection_link_identity "
        "ON projection_links (source_system_id, entity, source_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_projection_links_status "
        "ON projection_links (source_system_id, status)"
    )


def downgrade() -> None:
    op.drop_table("projection_links")
