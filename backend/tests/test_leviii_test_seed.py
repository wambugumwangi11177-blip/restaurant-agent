"""Env-gated Eleven Jack test seed — idempotent and password-safe."""

import os

import auth
import leviii_test_seed
import models
from tests.test_storekeeper_foundation import _tenant


def test_unset_env_is_noop(client, db_session, monkeypatch):
    monkeypatch.delenv("SEED_TEST_DATA", raising=False)
    monkeypatch.delenv("SEED_OWNER_PASSWORD", raising=False)
    leviii_test_seed.provision_test_data_from_env()
    assert db_session.query(models.Tenant).filter(models.Tenant.name == "Eleven").count() == 0


def test_seed_creates_owner_jack_and_sample_once(client, db_session, monkeypatch):
    monkeypatch.setenv("SEED_TEST_DATA", "1")
    monkeypatch.setenv("SEED_OWNER_PASSWORD", "ElevenOwner9")
    leviii_test_seed.provision_test_data_from_env()
    owner = db_session.query(models.User).filter_by(email="owner@eleven.leviii").one()
    assert auth.verify_password("ElevenOwner9", owner.hashed_password)
    jack = db_session.query(models.User).filter_by(email="jack@eleven.leviii").one()
    assert jack.hashed_password is None
    amina = db_session.query(models.User).filter_by(email="amina@eleven.leviii").one()
    assert amina.hashed_password is None
    restaurant = db_session.query(models.Restaurant).filter_by(tenant_id=owner.tenant_id).one()
    assert db_session.query(models.StockZone).filter_by(restaurant_id=restaurant.id).count() == 4
    assert db_session.query(models.InventoryItem).filter_by(restaurant_id=restaurant.id, item_name="Rice").one()

    leviii_test_seed.provision_test_data_from_env()
    db_session.expire_all()
    owner_again = db_session.query(models.User).filter_by(email="owner@eleven.leviii").one()
    assert auth.verify_password("ElevenOwner9", owner_again.hashed_password)


def test_ensure_direct_does_not_reset_owner_password(client, db_session):
    _tenant(db_session, "Eleven", "owner@eleven.leviii", password="KeepMeSafe9")
    leviii_test_seed.ensure_eleven_test_data(db_session, "DifferentPass9")
    db_session.expire_all()
    owner = db_session.query(models.User).filter_by(email="owner@eleven.leviii").one()
    assert auth.verify_password("KeepMeSafe9", owner.hashed_password)