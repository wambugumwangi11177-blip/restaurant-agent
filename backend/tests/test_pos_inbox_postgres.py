"""PostgreSQL-only upgrade, FK, trigger and simultaneous-delivery evidence."""
import importlib.util
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import sessionmaker

import models
from integration import inbox
from integration.inbox_models import PosAppliedRecord, PosInbox, PosParseAttempt, PosSourceBinding
from integration.models import Base as IntegrationBase, SourceSystem

URL = os.getenv("OWNER_POSTGRES_TEST_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requires isolated local PostgreSQL test_owner_release")


@pytest.fixture
def pg():
    parsed = urlparse(URL)
    if parsed.hostname not in ("localhost", "127.0.0.1") or parsed.path != "/test_owner_release":
        pytest.fail("Refusing a non-local or non-test database")
    engine = create_engine(URL, hide_parameters=True)
    yield engine
    engine.dispose()


def migrate(connection):
    path = Path(__file__).parents[1] / "alembic/versions/051_pos_durable_inbox.py"
    spec = importlib.util.spec_from_file_location("pos_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with Operations.context(MigrationContext.configure(connection)):
        module.upgrade()


def test_pos_upgrade_and_concurrent_deliveries(pg):
    # Representative prior schema (no new inbox tables), retaining all old rows.
    models.Base.metadata.create_all(pg, tables=[t for t in models.Base.metadata.sorted_tables if not t.name.startswith("pos_")])
    IntegrationBase.metadata.create_all(pg)
    Session = sessionmaker(bind=pg, autoflush=False)
    unique = uuid.uuid4().hex
    with Session() as db:
        tenant = models.Tenant(name="Synthetic inbox " + unique)
        db.add(tenant); db.flush()
        restaurant = models.Restaurant(tenant_id=tenant.id, name="Synthetic inbox")
        owner = models.User(tenant_id=tenant.id, email=unique + "@example.test",
                            hashed_password="not-a-credential", role=models.Role.ADMIN,
                            staff_role=models.StaffRole.OWNER)
        db.add_all([restaurant, owner]); db.commit()
        rid, uid = restaurant.id, owner.id
    with pg.begin() as connection:
        migrate(connection)
        migrate(connection)
        assert "pos_inbox" in inspect(connection).get_table_names()
    with Session() as db:
        assert db.get(models.User, uid).staff_role == models.StaffRole.OWNER
        binding = PosSourceBinding(slug="synthetic-" + unique, restaurant_id=rid)
        source = SourceSystem(slug="synthetic-" + unique, display_name="Synthetic test", mechanism="webhook")
        db.add_all([binding, source]); db.commit()
        binding_id, source_id = binding.id, source.id
        raw = json.dumps({"entity": "sale", "records": [{"id": unique, "total": "1.005"}]}).encode()
        receipts = [inbox.store_receipt(db, binding=binding, raw=raw) for _ in range(2)]
    def parse(receipt_id):
        with Session() as db:
            return inbox.parse_receipt(db, receipt_id, restaurant_id=rid, source_system_id=source_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(parse, receipts))
    assert sum(r["orders_inserted"] for r in results) == 1
    with Session() as db:
        assert db.query(models.Order).filter_by(restaurant_id=rid).one().total == 101
        assert db.query(PosAppliedRecord).filter_by(binding_id=binding_id).count() == 1
        assert db.query(PosParseAttempt).filter(PosParseAttempt.inbox_id.in_(receipts)).count() == 2
        db.add(PosInbox(id=str(uuid.uuid4()), binding_id=binding_id, restaurant_id=rid + 100_000,
                        raw_body="{}", payload_sha256="0" * 64))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    with pg.connect() as connection:
        with pytest.raises(DBAPIError):
            connection.execute(text("UPDATE pos_inbox SET raw_body = :raw WHERE id = :id"),
                               {"raw": "{}", "id": receipts[0]})
        connection.rollback()


def test_pos_fresh_create_all_then_upgrade(pg):
    models.Base.metadata.create_all(pg)
    with pg.begin() as connection:
        migrate(connection)
        names = set(inspect(connection).get_table_names())
        assert {"pos_source_bindings", "pos_inbox", "pos_applied_records", "pos_parse_attempts"} <= names
