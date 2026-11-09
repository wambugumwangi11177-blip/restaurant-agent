"""Add durable source-bound POS inbox; no copying or guessing historical evidence."""
from alembic import op
import sqlalchemy as sa

revision = "051_pos_durable_inbox"
down_revision = "050_creative_takes"
branch_labels = None
depends_on = None


def upgrade():
    # Freeze this schema; importing future ORM models would change old upgrades.
    metadata = sa.MetaData()
    sa.Table("restaurants", metadata, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("users", metadata, sa.Column("id", sa.Integer, primary_key=True))
    bindings = sa.Table("pos_source_bindings", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("restaurant_id", sa.Integer, sa.ForeignKey("restaurants.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("id", "restaurant_id", name="uq_pos_binding_scope"))
    inbox = sa.Table("pos_inbox", metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("binding_id", sa.Integer, nullable=False),
        sa.Column("restaurant_id", sa.Integer, nullable=False),
        sa.Column("raw_body", sa.Text, nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("received_at", sa.DateTime, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("parser_version", sa.String(48)),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("last_attempt_at", sa.DateTime),
        sa.Column("parsed_at", sa.DateTime),
        sa.Column("error_code", sa.String(48)),
        sa.Column("result", sa.JSON),
        sa.ForeignKeyConstraint(["binding_id", "restaurant_id"], ["pos_source_bindings.id", "pos_source_bindings.restaurant_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("id", "binding_id", name="uq_pos_inbox_source"),
        sa.Index("ix_pos_inbox_scope_status_time", "restaurant_id", "status", "received_at"))
    applied = sa.Table("pos_applied_records", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("binding_id", sa.Integer, nullable=False),
        sa.Column("inbox_id", sa.String(36), nullable=False),
        sa.Column("entity", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("source_version", sa.String(128), nullable=False),
        sa.Column("applied_at", sa.DateTime, nullable=False),
        sa.ForeignKeyConstraint(["inbox_id", "binding_id"], ["pos_inbox.id", "pos_inbox.binding_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("binding_id", "entity", "source_id", "source_version", name="uq_pos_applied_identity"))
    attempts = sa.Table("pos_parse_attempts", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("inbox_id", sa.String(36), sa.ForeignKey("pos_inbox.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("actor_id", sa.Integer, sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("parser_version", sa.String(48), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("error_code", sa.String(48)),
        sa.Column("attempted_at", sa.DateTime, nullable=False))
    for table in (bindings, inbox, applied, attempts):
        table.create(op.get_bind(), checkfirst=True)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE OR REPLACE FUNCTION protect_pos_envelope() RETURNS trigger AS $$
        BEGIN
            IF NEW.id IS DISTINCT FROM OLD.id OR NEW.binding_id IS DISTINCT FROM OLD.binding_id
               OR NEW.restaurant_id IS DISTINCT FROM OLD.restaurant_id
               OR NEW.raw_body IS DISTINCT FROM OLD.raw_body
               OR NEW.payload_sha256 IS DISTINCT FROM OLD.payload_sha256
               OR NEW.received_at IS DISTINCT FROM OLD.received_at THEN
                RAISE EXCEPTION 'POS envelope is immutable';
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
        op.execute("DROP TRIGGER IF EXISTS pos_envelope_immutable ON pos_inbox")
        op.execute("CREATE TRIGGER pos_envelope_immutable BEFORE UPDATE ON pos_inbox FOR EACH ROW EXECUTE FUNCTION protect_pos_envelope()")


def downgrade():
    # Evidence deletion requires an operator decision, never an automatic rollback.
    raise RuntimeError("Evidence-preserving migration: roll back code with durable inbox disabled; retain these tables.")
