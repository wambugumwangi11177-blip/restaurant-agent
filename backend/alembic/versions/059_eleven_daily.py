"""Add location evidence, receipt batches and daily review records without changing historical stock."""
from alembic import op
from models import Base
revision = '059_eleven_daily'
down_revision = '058_eleven_workflows'
branch_labels = None
depends_on = None
TABLES = ('stock_zone_events','stock_receipt_batches','daily_shift_closes')
def upgrade():
    for name in TABLES:
        Base.metadata.tables[name].create(op.get_bind(), checkfirst=not op.get_context().as_sql)
def downgrade():
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(op.get_bind(), checkfirst=not op.get_context().as_sql)
