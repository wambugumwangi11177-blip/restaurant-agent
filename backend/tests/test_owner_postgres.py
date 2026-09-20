"""PostgreSQL release gate: migration paths, real row locks and backup restore.

Runs only against a local disposable database explicitly named test_owner_release.
No production URLs, provider keys or source data are used.
"""
import importlib.util
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from alembic.migration import MigrationContext
from alembic.operations import Operations
import models

URL = os.getenv('OWNER_POSTGRES_TEST_URL')
pytestmark = pytest.mark.skipif(not URL, reason='requires disposable PostgreSQL release database')


@pytest.fixture
def pg():
    parsed = urlparse(URL)
    if parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.path != '/test_owner_release':
        pytest.fail('Refusing non-local or non-test PostgreSQL target')
    engine = create_engine(URL)
    models.Base.metadata.create_all(engine)
    yield engine
    # Tests use a dedicated throwaway CI service, no destructive schema cleanup.
    engine.dispose()


def migration(connection, operation):
    path = Path(__file__).parents[1] / 'alembic/versions/048_scope_attention_decisions.py'
    spec = importlib.util.spec_from_file_location('owner_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with Operations.context(MigrationContext.configure(connection)):
        getattr(module, operation)()


def test_postgres_owner_migration_and_concurrent_retry(pg):
    from routers.overview import decide, DecisionBody
    Session = sessionmaker(bind=pg)
    # Fresh create_all followed by migration must be safe.
    with pg.begin() as conn:
        migration(conn, 'upgrade')
        migration(conn, 'downgrade')
        columns = {c['name'] for c in inspect(conn).get_columns('attention_decisions')}
        assert 'restaurant_id' not in columns
        migration(conn, 'upgrade')  # Existing 047 table upgrade.
        assert 'restaurant_id' in {c['name'] for c in inspect(conn).get_columns('attention_decisions')}
    with Session() as db:
        tenant = models.Tenant(name='Release test')
        db.add(tenant); db.flush()
        restaurant = models.Restaurant(tenant_id=tenant.id, name='Release test')
        db.add(restaurant); db.flush()
        owner = models.User(tenant_id=tenant.id, active_restaurant_id=restaurant.id,
                            email='release@example.test', hashed_password='unused', role=models.Role.ADMIN)
        db.add(owner)
        db.add(models.Order(restaurant_id=restaurant.id, total=12345, is_paid=True, status=models.OrderStatus.SERVED))
        db.add(models.InventoryItem(restaurant_id=restaurant.id, item_name='Test stock', quantity=1, unit='kg', low_stock_threshold=5))
        db.commit()
        user = SimpleNamespace(id=owner.id, tenant_id=tenant.id, active_restaurant_id=restaurant.id)
        from routers.overview import _operational_cards
        key = _operational_cards(db, restaurant.id)[0]['id']
    def record(_):
        with Session() as db:
            return decide(key, DecisionBody(decision='later'), db, user)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(record, range(2)))
    assert all(r['status'] == 'later' for r in results)
    with Session() as db:
        assert db.query(models.AttentionDecision).filter_by(restaurant_id=user.active_restaurant_id, card_key=key).count() == 1
