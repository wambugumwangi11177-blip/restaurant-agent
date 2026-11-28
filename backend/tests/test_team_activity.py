import json

import models
from tests.test_cash_close import _finish_setup
from tests.test_store_intake import JPEG, _day_photos
from tests.test_storekeeper_foundation import _add_staff, _auth, _tenant, _token, _unlock

_RECEIVE = [("invoice", ("invoice.jpg", JPEG, "image/jpeg")), ("goods", ("goods.jpg", JPEG, "image/jpeg"))]


def _delivery(client, jack, rice_id):
    sup = client.post(
        "/api/v1/store/suppliers",
        headers=_auth(_token(jack)),
        json={"name": "Farm", "phone": "", "brings": "main food"},
    ).json()
    saved = client.post(
        "/api/v1/store/deliveries",
        headers=_auth(_token(jack)),
        data={"supplier_id": str(sup["id"]), "lines": json.dumps([{"item_id": rice_id, "quantity": 3}])},
        files=_RECEIVE,
    )
    assert saved.status_code == 201, saved.text


def _stack(client, db_session, tag):
    tenant, owner, restaurant = _tenant(db_session, "Eleven", f"owner-{tag}@eleven.leviii")
    jack = _add_staff(db_session, tenant, restaurant, f"jack-{tag}@eleven.leviii", models.StaffRole.STOCKKEEPER)
    amina = _add_staff(db_session, tenant, restaurant, f"amina-{tag}@eleven.leviii", models.StaffRole.CONTROLLER)
    _finish_setup(db_session, amina, restaurant)
    _unlock(client, jack)
    return owner, jack, amina, restaurant


def test_owner_reads_deliveries_with_lines_photos_and_eat_times(client, db_session):
    owner, jack, _amina, _restaurant = _stack(client, db_session, "feed")
    client.post(
        "/api/v1/store/items/opening",
        headers=_auth(_token(jack)),
        json={"item_name": "Rice", "quantity": 5, "unit": "kg", "zone": "Main store"},
    )
    _day_photos(client, jack, "open")
    rice = next(i for i in client.get("/api/v1/store/items", headers=_auth(_token(jack))).json()["items"] if i["item_name"] == "Rice")
    _delivery(client, jack, rice["id"])

    feed = client.get("/api/v1/eleven/team-activity", headers=_auth(_token(owner)))
    assert feed.status_code == 200, feed.text
    body = feed.json()
    assert body["timezone"] == "Africa/Nairobi"
    delivery = next(e for e in body["events"] if e["label"] == "Received a delivery")
    assert delivery["person_name"] == "jack-feed"
    assert delivery["lines"] == [{"item": "Rice", "quantity": 3.0, "unit": "kg"}]
    assert {p["label"] for p in delivery["photos"]} == {"invoice", "goods"}
    assert delivery["at"].endswith("+03:00")
    assert len(delivery["time"]) == 5
    for photo in delivery["photos"]:
        fetched = client.get(photo["path"], headers=_auth(_token(owner)))
        assert fetched.status_code == 200
    assert any(e["label"] == "Counted a stock item" for e in body["events"])
    assert any(photo["label"] == "store" for e in body["events"] for photo in e["photos"])


def test_feed_filters_by_person_and_hides_model_wording(client, db_session):
    owner, jack, amina, _restaurant = _stack(client, db_session, "who")
    client.post(
        "/api/v1/store/items/opening",
        headers=_auth(_token(jack)),
        json={"item_name": "Rice", "quantity": 5, "unit": "kg", "zone": "Main store"},
    )
    _day_photos(client, jack, "open")
    rice = next(i for i in client.get("/api/v1/store/items", headers=_auth(_token(jack))).json()["items"] if i["item_name"] == "Rice")
    _delivery(client, jack, rice["id"])
    client.post("/api/v1/auth/login", json={"email": amina.email, "password": "TempPass1"})
    db_session.add(models.StaffEntryAudit(
        restaurant_id=_restaurant.id, user_id=jack.id, action="delivery_ai_mismatch", entity_type="delivery_receipt",
        summary="AI: Rice on delivery 1 do not match the photos. Qwen wrote the note after DeepSeek failed.",
        detail_json="{}",
    ))
    db_session.add(models.StaffEntryAudit(
        restaurant_id=_restaurant.id, user_id=jack.id, action="delivery_ai_unavailable", entity_type="delivery_receipt",
        summary="AI check unavailable for delivery 1.", detail_json="{}",
    ))
    db_session.commit()

    everyone = client.get("/api/v1/eleven/team-activity", headers=_auth(_token(owner))).json()
    assert {p["name"] for p in everyone["people"]} == {"jack-who", "amina-who"}
    only = client.get(f"/api/v1/eleven/team-activity?person={amina.id}", headers=_auth(_token(owner))).json()
    assert [(e["label"], e["summary"]) for e in only["events"]] == [("Signed in", "")]
    assert {e["person_name"] for e in only["events"]} == {"amina-who"}
    text = json.dumps(everyone)
    for word in ("AI:", "Qwen", "DeepSeek"):
        assert word not in text
    check = next(e for e in everyone["events"] if e["label"] == "Photo check")
    assert check["summary"] == "Delivery does not match the photos."
    assert check["needs_attention"] is True
    assert [e["label"] for e in everyone["events"]].count("Photo check") == 1


def test_feed_pages_back_with_before(client, db_session):
    owner, jack, amina, _restaurant = _stack(client, db_session, "page")
    for _ in range(3):
        client.post("/api/v1/auth/login", json={"email": amina.email, "password": "TempPass1"})
    first = client.get("/api/v1/eleven/team-activity?limit=2", headers=_auth(_token(owner))).json()
    assert len(first["events"]) == 2 and first["has_more"] is True
    rest = client.get(f"/api/v1/eleven/team-activity?limit=2&before={first['events'][-1]['id']}", headers=_auth(_token(owner))).json()
    assert rest["problems"] == []
    assert all(e["id"] < first["events"][-1]["id"] for e in rest["events"])


def test_only_the_owner_reads_the_feed(client, db_session):
    owner, jack, amina, _restaurant = _stack(client, db_session, "gate")
    assert client.get("/api/v1/eleven/team-activity", headers=_auth(_token(jack))).status_code == 403
    assert client.get("/api/v1/eleven/team-activity", headers=_auth(_token(amina))).status_code == 403
    assert client.get("/api/v1/eleven/team-activity").status_code == 401


def test_staff_screen_problems_reach_the_owner(client, db_session):
    owner, jack, amina, _restaurant = _stack(client, db_session, "err")
    sent = client.post(
        "/api/v1/client-errors",
        headers=_auth(_token(jack)),
        json={"kind": "request", "screen": "/store/deliveries", "message": "POST /api/v1/store/deliveries failed: Photo too large", "status_code": 413},
    )
    assert sent.status_code == 202 and sent.json() == {"stored": True}
    client.post(
        "/api/v1/client-errors",
        headers=_auth(_token(amina)),
        json={"kind": "script", "screen": "/store/close", "message": "Cannot read properties of undefined"},
    )
    body = client.get("/api/v1/eleven/team-activity", headers=_auth(_token(owner))).json()
    assert [(p["person_name"], p["kind"], p["screen"], p["status_code"]) for p in body["problems"]] == [
        ("amina-err", "script", "/store/close", None),
        ("jack-err", "request", "/store/deliveries", 413),
    ]
    assert body["problems"][0]["at"].endswith("+03:00")
    only = client.get(f"/api/v1/eleven/team-activity?person={jack.id}", headers=_auth(_token(owner))).json()
    assert [p["person_name"] for p in only["problems"]] == ["jack-err"]


def test_problem_reports_are_checked_and_capped(client, db_session):
    owner, jack, _amina, _restaurant = _stack(client, db_session, "cap")
    headers = _auth(_token(jack))
    assert client.post("/api/v1/client-errors", json={"kind": "script", "screen": "/x", "message": "m"}).status_code == 401
    assert client.post("/api/v1/client-errors", headers=headers, json={"kind": "other", "screen": "/x", "message": "m"}).status_code == 422
    assert client.post("/api/v1/client-errors", headers=headers, json={"kind": "script", "screen": "/x", "message": "m" * 1001}).status_code == 422
    stored = [
        client.post("/api/v1/client-errors", headers=headers, json={"kind": "script", "screen": "/x", "message": f"m{i}"}).json()["stored"]
        for i in range(25)
    ]
    assert stored.count(True) == 20
    assert db_session.query(models.ClientError).count() == 20


def test_signing_in_is_recorded_for_staff_only(client, db_session):
    owner, jack, _amina, restaurant = _stack(client, db_session, "login")
    assert client.post("/api/v1/auth/login", json={"email": owner.email, "password": "Ownerpass1"}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": jack.email, "password": "TempPass1"}).status_code == 200
    rows = db_session.query(models.StaffEntryAudit).filter_by(action="signed_in").all()
    assert [r.user_id for r in rows] == [jack.id]
