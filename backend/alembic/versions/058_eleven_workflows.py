"""Owner scheduled prices and retry-safe staff operation journal."""
from alembic import op
import sqlalchemy as sa

revision = '058_eleven_workflows'
down_revision = '057_eleven_readiness'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('scheduled_menu_prices',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('restaurant_id', sa.Integer(), sa.ForeignKey('restaurants.id'), nullable=False),
        sa.Column('menu_item_id', sa.Integer(), sa.ForeignKey('menu_items.id'), nullable=False),
        sa.Column('channel', sa.String(32), nullable=False), sa.Column('daypart', sa.String(16), nullable=False),
        sa.Column('price_cents', sa.Integer(), nullable=False), sa.Column('starts_on', sa.Date(), nullable=False),
        sa.Column('ends_on', sa.Date()), sa.Column('explanation', sa.String(240), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False), sa.Column('is_active', sa.Boolean(), nullable=False))
    op.create_index('ix_scheduled_menu_prices_restaurant_id', 'scheduled_menu_prices', ['restaurant_id'])
    op.create_table('operation_entries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('restaurant_id', sa.Integer(), sa.ForeignKey('restaurants.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('entry_key', sa.String(120), nullable=False, unique=True),
        sa.Column('kind', sa.String(20), nullable=False), sa.Column('payload', sa.Text(), nullable=False),
        sa.Column('result', sa.Text(), nullable=False), sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('undone_at', sa.DateTime()))
    op.create_index('ix_operation_entries_restaurant_id', 'operation_entries', ['restaurant_id'])


def downgrade():
    op.drop_table('operation_entries')
    op.drop_table('scheduled_menu_prices')
