"""Questionnaire, suppliers, deliveries, and the quiet photo check."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import models
from money_visibility import money_keys_in
from tests.test_storekeeper_foundation import _add_staff, _auth, _tenant, _token

JPEG = b"\xff\xd8\xff\xd9"


def _answer(client, user, question_id, value, suppliers=None):
    body = {"question_id": question_id, "value": value}
    if suppliers is not None:
        body["suppliers"] = suppliers
    return client.post(
        "/api/v1/staff-setup/questionnaire",
        headers=_auth(_token(user)),
        json=body,
    )


def _unlock(client, jack):
    steps = (
        ("receives_deliveries", "yes", None),
        ("supplier_list", "listed", [{"name": "Unlock Supply", "brings": "Main food", "arrival": "phone"}]),
        ("stock_in_pos", "no", None),
        ("issues_to_kitchen", "yes", None),
        ("records_waste", "yes", None),
        ("closes_the_day", "me", None),
        ("knows_running_costs", "yes", None),
    )
    for question_id, value, suppliers in steps:
        response = _answer(client, jack, question_id, value, suppliers)
        assert response.status_code == 200, response.text


def test_questions_route_delegate_and_show_on_the_owner_feed(client, db_session):
    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner-q@eleven.leviii")
    jack = _add_staff(db_session, tenant, restaurant, "jack-q@eleven.leviii", models.StaffRole.STOCKKEEPER)
    early = _answer(client, jack, "receives_deliveries", "yes")
    assert early.status_code == 200
    assert early.json()["opens"] == "/store/deliveries"
    assert "deliveries" in early.json()["unlocked_modules"]
    delegated = _answer(client, jack, "knows_running_costs", "unknown")
    assert delegated.status_code == 200
    assert delegated.json()["delegated"] is True
    activity = client.get("/api/v1/staff-setup/activity", headers=_auth(_token(owner)))
    person = activity.json()["people"][0]
    assert person["answers"][0]["question_id"] == "receives_deliveries"
    summaries = " ".join(entry["summary"] for entry in activity.json()["entries"])
    assert "Sent to the accountant" in summaries
    assert "1234" not in summaries


def test_suppliers_stock_issue_and_waste_are_quantities_only(client, db_session):
    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner-stock@eleven.leviii")
    jack = _add_staff(db_session, tenant, restaurant, "jack-stock@eleven.leviii", models.StaffRole.STOCKKEEPER)
    locked = client.post(
        "/api/v1/store/suppliers",
        headers=_auth(_token(jack)),
        json={"name": "Farm", "phone": "0700111222", "brings": "main food"},
    )
    assert locked.status_code == 403
    _unlock(client, jack)
    created = client.post(
        "/api/v1/store/suppliers",
        headers=_auth(_token(jack)),
        json={"name": "Farm", "phone": "0700111222", "brings": "main food"},
    )
    assert created.status_code == 201
    assert money_keys_in(created.json()) == []
    zones = client.get("/api/v1/store/zones", headers=_auth(_token(jack)))
    assert [zone["name"] for zone in zones.json()] == ["Main store", "Cold room", "Bar", "Kitchen"]
    blocked = client.post(
        "/api/v1/store/items/opening",
        headers=_auth(_token(jack)),
        json={"item_name": "Tusker", "quantity": 24, "unit": "bottle", "zone": "Bar"},
    )
    assert blocked.status_code == 403
    setup = client.get("/api/v1/staff-setup", headers=_auth(_token(jack))).json()
    assert setup["stock_followup"]["status"] == "count_when_live"
    assert setup["stock_followup"]["pending"]
    assert "opening-count" not in setup["unlocked_modules"]
    opening = client.post(
        "/api/v1/store/items/opening",
        headers=_auth(_token(owner)),
        json={
            "item_name": "Tusker",
            "quantity": 24,
            "unit": "bottle",
            "zone": "Bar",
            "buying_unit": "crate",
            "units_per_buy": 24,
            "yield_fraction": 1,
        },
    )
    assert opening.status_code == 201, opening.text
    again = client.post(
        "/api/v1/store/items/opening",
        headers=_auth(_token(owner)),
        json={"item_name": "Tusker", "quantity": 10, "unit": "bottle", "zone": "Bar"},
    )
    assert again.status_code == 409
    items = client.get("/api/v1/store/items", headers=_auth(_token(jack))).json()["items"]
    tusker = next(item for item in items if item["item_name"] == "Tusker")
    assert tusker["buying_unit"] == "crate"
    assert tusker["units_per_buy"] == 24
    assert tusker["quantity"] == 24
    assert money_keys_in(items) == []
    issued = client.post(
        "/api/v1/store/issue",
        headers=_auth(_token(jack)),
        json={"item_id": tusker["id"], "quantity": 4, "from_zone": "Bar", "to_zone": "Cold room"},
    )
    assert issued.status_code == 201
    kitchen = client.post(
        "/api/v1/store/issue",
        headers=_auth(_token(jack)),
        json={"item_id": tusker["id"], "quantity": 1, "from_zone": "Bar", "to_zone": "Kitchen"},
    )
    assert kitchen.status_code == 400
    after = client.get("/api/v1/store/items", headers=_auth(_token(jack))).json()["items"]
    left = next(item for item in after if item["id"] == tusker["id"])
    assert left["quantity"] == 24
    costs = client.post(
        "/api/v1/store/costs",
        headers=_auth(_token(jack)),
        json={"kind": "rent", "label": "Rent", "amount_kes": 15000},
    )
    assert costs.status_code == 201
    hidden = client.get("/api/v1/store/costs", headers=_auth(_token(jack)))
    assert hidden.status_code == 200
    assert money_keys_in(hidden.json()) == []
    assert hidden.json()["costs"][0]["label"] == "Rent"
    visible = client.get("/api/v1/store/costs", headers=_auth(_token(owner)))
    assert visible.json()["costs"][0]["amount_cents"] == 1_500_000
    audit = db_session.query(models.StaffEntryAudit).filter_by(action="running_cost_added").one()
    assert "15000" not in audit.summary
    assert "1500000" not in audit.detail_json


def test_delivery_needs_both_photos_and_ai_mismatch_stays_with_the_owner(client, db_session):
    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner-del@eleven.leviii")
    jack = _add_staff(db_session, tenant, restaurant, "jack-del@eleven.leviii", models.StaffRole.STOCKKEEPER)
    cook = _add_staff(db_session, tenant, restaurant, "cook-del@eleven.leviii", models.StaffRole.KITCHEN)
    _unlock(client, jack)
    supplier = client.post(
        "/api/v1/store/suppliers",
        headers=_auth(_token(jack)),
        json={"name": "Fresh Farm", "phone": "", "brings": "main food"},
    ).json()
    missing_goods = client.post(
        "/api/v1/store/deliveries",
        headers=_auth(_token(jack)),
        data={"supplier_id": str(supplier["id"]), "lines": json.dumps([{"item_name": "Rice", "quantity": 8, "unit": "kg"}])},
        files={"invoice": ("invoice.jpg", JPEG, "image/jpeg")},
    )
    assert missing_goods.status_code == 422
    priced = client.post(
        "/api/v1/store/deliveries",
        headers=_auth(_token(jack)),
        data={
            "supplier_id": str(supplier["id"]),
            "lines": json.dumps([{"item_name": "Rice", "quantity": 8, "unit": "kg", "price": 100}]),
        },
        files=[
            ("invoice", ("invoice.jpg", JPEG, "image/jpeg")),
            ("goods", ("goods.jpg", JPEG, "image/jpeg")),
        ],
    )
    assert priced.status_code == 422
    reading = {
        "supplier": "Fresh Farm",
        "invoice_items": [{"name": "Rice", "quantity": 3, "unit": "kg"}],
        "goods_items": [{"name": "Rice", "quantity": 8, "unit": "kg"}],
    }
    explained = {
        "note": "The invoice shows 3 kg of Rice and you keyed 8 kg.",
        "match": False,
        "mismatches": [{"item_name": "Rice", "source": "invoice", "keyed": 8, "seen": 3}],
        "model": "deepseek/deepseek-v4-flash",
        "fell_back": False,
        "ungrounded": [],
    }
    with patch("store_vision.ask_model", return_value=reading), patch("store_vision.explain_difference", return_value=explained):
        saved = client.post(
            "/api/v1/store/deliveries",
            headers=_auth(_token(jack)),
            data={
                "supplier_id": str(supplier["id"]),
                "lines": json.dumps([{"item_name": "Rice", "quantity": 8, "unit": "kg"}]),
            },
            files=[
                ("invoice", ("invoice.jpg", JPEG, "image/jpeg")),
                ("goods", ("goods.jpg", JPEG, "image/jpeg")),
            ],
        )
    assert saved.status_code == 201, saved.text
    body = saved.json()
    assert money_keys_in(body) == []
    assert "http" not in json.dumps(body)
    assert "mismatches" not in body
    body = client.get("/api/v1/store/deliveries", headers=_auth(_token(jack))).json()[0]
    assert body["ai"] == "checked"
    assert {photo["kind"] for photo in body["photos"]} == {"invoice", "goods"}
    rice = db_session.query(models.InventoryItem).filter_by(item_name="Rice").one()
    assert rice.quantity == 8
    assert rice.cost_per_unit == 0
    owner_view = client.get("/api/v1/store/deliveries", headers=_auth(_token(owner))).json()[0]
    assert owner_view["ai_label"] == "AI"
    assert owner_view["mismatches"][0]["seen"] == 3
    assert "3 kg" in owner_view["ai_note"]
    jack_view = client.get("/api/v1/store/deliveries", headers=_auth(_token(jack))).json()[0]
    assert "mismatches" not in jack_view
    assert "ai_note" not in jack_view
    photo_id = body["photos"][0]["id"]
    photo = client.get(
        f"/api/v1/store/deliveries/{body['id']}/photos/{photo_id}",
        headers=_auth(_token(jack)),
    )
    assert photo.status_code == 200
    assert photo.content.startswith(b"\xff\xd8")
    hidden = client.get(
        f"/api/v1/store/deliveries/{body['id']}/photos/{photo_id}",
        headers=_auth(_token(cook)),
    )
    assert hidden.status_code == 403
    priced_by_jack = client.post(
        f"/api/v1/store/deliveries/{body['id']}/prices",
        headers=_auth(_token(jack)),
        json={"lines": [{"line_id": body["lines"][0]["id"], "cost_per_unit_kes": 120}]},
    )
    assert priced_by_jack.status_code == 403
    priced_by_owner = client.post(
        f"/api/v1/store/deliveries/{body['id']}/prices",
        headers=_auth(_token(owner)),
        json={"lines": [{"line_id": body["lines"][0]["id"], "cost_per_unit_kes": 120}]},
    )
    assert priced_by_owner.status_code == 200
    db_session.refresh(rice)
    assert rice.cost_per_unit == 120
    jack_stock = client.get("/api/v1/inventory/", headers=_auth(_token(jack)))
    assert money_keys_in(jack_stock.json()) == []
    notes = db_session.query(models.Notification).all()
    assert all("AI" not in (note.title or "") and "AI" not in (note.body or "") for note in notes)
    assert db_session.query(models.StaffEntryAudit).filter_by(action="delivery_ai_mismatch").count() == 1


def test_ai_failure_is_named_and_the_call_does_not_change_model(client, db_session, monkeypatch):
    tenant, _owner, restaurant = _tenant(db_session, "Eleven", "owner-ai@eleven.leviii")
    jack = _add_staff(db_session, tenant, restaurant, "jack-ai@eleven.leviii", models.StaffRole.STOCKKEEPER)
    _answer(client, jack, "receives_deliveries", "yes")
    _answer(client, jack, "supplier_list", "listed", suppliers=[{"name": "Farm", "brings": "Alcohol", "arrival": "phone"}])
    supplier = client.get("/api/v1/store/suppliers", headers=_auth(_token(jack))).json()[0]
    called = {"text": False}

    def text_model(*_args, **_kwargs):
        called["text"] = True
        raise RuntimeError("should not run")

    with patch("store_vision.ask_model", side_effect=RuntimeError("down")), patch("store_vision.explain_difference", side_effect=text_model):
        saved = client.post(
            "/api/v1/store/deliveries",
            headers=_auth(_token(jack)),
            data={
                "supplier_id": str(supplier["id"]),
                "lines": json.dumps([{"item_name": "Beer", "quantity": 2, "unit": "crate"}]),
            },
            files=[
                ("invoice", ("invoice.jpg", JPEG, "image/jpeg")),
                ("goods", ("goods.jpg", JPEG, "image/jpeg")),
            ],
        )
    assert saved.status_code == 201, saved.text
    assert called["text"] is False
    listed = client.get("/api/v1/store/deliveries", headers=_auth(_token(jack))).json()[0]
    assert listed["ai_label"] == "AI check unavailable"
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        message = SimpleNamespace(content='{"supplier":"","invoice_items":[],"goods_items":[]}')
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr("ai.llm_client._PROVIDER", "openrouter")
    monkeypatch.setattr("ai.llm_client._get_client", lambda: fake)
    from ai.llm_client import chat_with_images
    chat_with_images("read this", [("image/jpeg", JPEG)])
    assert captured["model"] == "qwen/qwen3.7-flash"
    assert captured["extra_body"]["reasoning"] == {"enabled": False}
    assert captured["extra_body"]["provider"] == {"data_collection": "deny"}
    assert captured["messages"][0]["content"][1]["type"] == "image_url"
    monkeypatch.setattr("ai.llm_client._PROVIDER", "groq")
    try:
        chat_with_images("read this", [("image/jpeg", JPEG)])
        raised = False
    except RuntimeError:
        raised = True
    assert raised


def test_supplier_answers_prefill_records_and_pos_status_is_visible(client, db_session):
    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner-pos@eleven.leviii")
    jack = _add_staff(db_session, tenant, restaurant, "jack-pos@eleven.leviii", models.StaffRole.STOCKKEEPER)
    _answer(client, jack, "receives_deliveries", "yes")
    named = _answer(client, jack, "supplier_list", "listed", suppliers=[
        {"name": "Keittas", "brings": "Alcohol", "arrival": "scheduled"},
        {"name": "Farm", "brings": "Main food", "arrival": "pickup"},
    ])
    assert named.status_code == 200, named.text
    rows = {row["name"]: row for row in client.get("/api/v1/store/suppliers", headers=_auth(_token(jack))).json()}
    assert rows["Keittas"]["arrival"] == "scheduled"
    assert rows["Keittas"]["arrival_label"] == "Scheduled delivery"
    assert rows["Farm"]["brings"] == "Main food"
    again = _answer(client, jack, "supplier_list", "listed", suppliers=[
        {"name": "keittas", "brings": "Alcohol", "arrival": "phone"},
    ])
    assert again.status_code == 200, again.text
    rows = client.get("/api/v1/store/suppliers", headers=_auth(_token(jack))).json()
    keittas = [row for row in rows if row["name"].lower() == "keittas"]
    assert len(keittas) == 1
    assert keittas[0]["arrival"] == "phone"
    assert db_session.query(models.StaffEntryAudit).filter_by(action="supplier_prefilled").count() == 1

    waiting = _answer(client, jack, "stock_in_pos", "yes")
    assert waiting.status_code == 200
    setup = client.get("/api/v1/staff-setup", headers=_auth(_token(jack))).json()
    assert setup["stock_followup"]["status"] == "waiting_on_pos"
    assert "opening-count" not in setup["unlocked_modules"]
    blocked = client.post(
        "/api/v1/store/items/opening",
        headers=_auth(_token(jack)),
        json={"item_name": "Rice", "quantity": 1, "unit": "kg"},
    )
    assert blocked.status_code == 403

    later = _answer(client, jack, "stock_in_pos", "no")
    assert later.status_code == 200
    setup = client.get("/api/v1/staff-setup", headers=_auth(_token(jack))).json()
    assert setup["stock_followup"]["status"] == "count_when_live"
    assert "real data" in setup["stock_followup"]["pending"]
    activity = client.get("/api/v1/staff-setup/activity", headers=_auth(_token(owner))).json()
    assert activity["people"][0]["stock_followup"]["status"] == "count_when_live"
    answer = next(item for item in activity["people"][0]["answers"] if item["question_id"] == "stock_in_pos")
    assert answer["value"] == "no"


def test_photo_model_is_configurable_and_the_note_stays_grounded(monkeypatch):
    captured = []

    def create(**kwargs):
        captured.append(kwargs)
        content = kwargs["messages"][0]["content"]
        if isinstance(content, list):
            body = '{"supplier":"Farm","invoice_items":[{"name":"Rice","quantity":3,"unit":"kg"}],"goods_items":[{"name":"Rice","quantity":8,"unit":"kg","weight":"about 8 kg"}]}'
        else:
            assert isinstance(content, str)
            assert "image_url" not in content
            body = '{"match":false,"note":"plain","mismatches":[]}'
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=body))])

    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setenv("OPENROUTER_VISION_MODEL", "vendor/cheaper-vision")
    monkeypatch.setattr("ai.llm_client._PROVIDER", "openrouter")
    monkeypatch.setattr("ai.llm_client._get_client", lambda: fake)
    from store_vision import ask_model, explain_difference

    reading = ask_model([("image/jpeg", JPEG)])
    assert captured[0]["model"] == "vendor/cheaper-vision"
    assert captured[0]["messages"][0]["content"][1]["type"] == "image_url"
    text_calls = []

    def chat_plain(prompt, *, model, max_tokens=500):
        text_calls.append(model)
        assert "image_url" not in prompt
        if model == "deepseek/deepseek-v4-flash":
            raise RuntimeError("down")
        return '{"match":false,"note":"The invoice shows 3 kg of Rice and you keyed 8 kg. Ignore the 99 kg.","mismatches":[{"item_name":"Rice","source":"invoice","keyed":8,"seen":3}]}'

    monkeypatch.setattr("store_vision.chat_plain", chat_plain)
    explained = explain_difference(reading, [{"item_name": "Rice", "quantity": 8, "unit": "kg"}])
    assert text_calls == ["deepseek/deepseek-v4-flash", "qwen/qwen3.7-flash"]
    assert explained["fell_back"] is True
    assert explained["model"] == "qwen/qwen3.7-flash"
    assert "99" not in explained["note"]
    assert "[unverified]" in explained["note"]
    assert "3" in explained["note"]

    def boom(prompt, *, model, max_tokens=500):
        raise RuntimeError(model)

    monkeypatch.setattr("store_vision.chat_plain", boom)
    try:
        explain_difference(reading, [{"item_name": "Rice", "quantity": 8, "unit": "kg"}])
        raised = False
    except RuntimeError:
        raised = True
    assert raised
