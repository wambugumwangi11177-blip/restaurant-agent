import models
from time_utils import utcnow
from tests.test_storekeeper_foundation import _add_staff, _auth, _tenant, _token, _unlock


def _finish_setup(db, user, restaurant):
    done = utcnow()
    db.add(models.StaffSetupProgress(
        user_id=user.id,
        restaurant_id=restaurant.id,
        updated_at=done,
        account_completed_at=done,
        questionnaire_completed_at=done,
        recipes_completed_at=done,
    ))
    db.commit()


CASH = {"cash_counted_kes": 1500, "mpesa_counted_kes": 800, "notes": "all counted"}


def test_only_the_accountant_or_manager_closes_cash(client, db_session):
    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner-cash@eleven.leviii")
    jack = _add_staff(db_session, tenant, restaurant, "jack-cash@eleven.leviii", models.StaffRole.STOCKKEEPER)
    amina = _add_staff(db_session, tenant, restaurant, "amina-cash@eleven.leviii", models.StaffRole.CONTROLLER)
    _unlock(client, jack)
    _finish_setup(db_session, amina, restaurant)

    jack_status = client.get("/api/v1/store/cash-close/status", headers=_auth(_token(jack)))
    assert jack_status.status_code == 403
    assert client.post("/api/v1/store/cash-close", headers=_auth(_token(jack)), json=CASH).status_code == 403

    status = client.get("/api/v1/store/cash-close/status", headers=_auth(_token(amina)))
    assert status.status_code == 200, status.text
    assert status.json()["cash_closed"] is False

    saved = client.post("/api/v1/store/cash-close", headers=_auth(_token(amina)), json=CASH)
    assert saved.status_code == 201, saved.text
    assert client.post("/api/v1/store/cash-close", headers=_auth(_token(amina)), json=CASH).status_code == 409
    after = client.get("/api/v1/store/cash-close/status", headers=_auth(_token(amina))).json()
    assert after["cash_closed"] is True
    assert after["cash_counted_kes"] == 1500
    assert after["mpesa_counted_kes"] == 800

    owner_note = (
        db_session.query(models.Notification)
        .filter_by(user_id=owner.id, event_type="day_cash_close")
        .count()
    )
    assert owner_note == 1


def test_a_manager_who_answered_the_close_question_can_close_cash(client, db_session):
    tenant, _, restaurant = _tenant(db_session, "Eleven", "owner-mgr@eleven.leviii")
    manager = _add_staff(db_session, tenant, restaurant, "mgr-cash@eleven.leviii", models.StaffRole.MANAGER)
    _finish_setup(db_session, manager, restaurant)
    locked = client.get("/api/v1/store/cash-close/status", headers=_auth(_token(manager)))
    assert locked.status_code == 403
    db_session.add(models.StaffSetupAnswer(
        user_id=manager.id,
        restaurant_id=restaurant.id,
        question_id="closes_the_day",
        value="me",
        unlocks="day-close",
    ))
    db_session.commit()
    saved = client.post("/api/v1/store/cash-close", headers=_auth(_token(manager)), json=CASH)
    assert saved.status_code == 201, saved.text
