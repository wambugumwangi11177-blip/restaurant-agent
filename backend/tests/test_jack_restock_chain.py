"""Jack journey: low stock should auto-draft PO and show Waiting on Owner (no test nudge)."""
from tests.test_storekeeper_foundation import _add_staff, _auth, _tenant, _token

QUESTIONS = {
    "ordering_method": "owner_approves",
    "receives_deliveries": "yes",
    "supplier_list": ("listed", [{"name": "Deep E2E Supply", "brings": "Main food", "arrival": "phone"}]),
    "stock_in_pos": "no",
    "issues_to_kitchen": "yes",
    "records_waste": "yes",
    "closes_the_day": "me",
    "knows_running_costs": "no",
    "zones": "listed",
    "buying_units": "no",
    "handover_who": "chef_pin",
    "handover_when": "once",
    "has_scale": "yes",
    "waste_approver": "owner",
    "count_rhythm": "weekly",
    "par_and_max": "per_item",
    "who_pays": "accountant",
    "prep_ahead": "no",
    "portions": "measured",
}


def _answer_all(client, jack):
    for qid, spec in QUESTIONS.items():
        if isinstance(spec, tuple):
            value, suppliers = spec
            body = {"question_id": qid, "value": value, "suppliers": suppliers}
        else:
            body = {"question_id": qid, "value": spec}
        res = client.post(
            "/api/v1/staff-setup/questionnaire",
            headers=_auth(_token(jack)),
            json=body,
        )
        assert res.status_code == 200, res.text


def test_jack_opening_handover_waste_auto_restock_inbox(client, db_session):
    tenant, owner, restaurant = _tenant(db_session, "Eleven (empty)", "owner-chain@eleven.leviii")
    jack = _add_staff(
        db_session,
        tenant,
        restaurant,
        "jack-chain@eleven.leviii",
        staff_role=__import__("models").StaffRole.STOCKKEEPER,
        must_change=False,
    )
    restaurant.restock_routing_mode = "unknown"
    db_session.commit()
    _answer_all(client, jack)
    setup = client.get("/api/v1/staff-setup", headers=_auth(_token(jack))).json()
    assert setup["steps"][-1]["state"] == "done" or any(
        s["id"] == "questionnaire" and s["state"] == "done" for s in setup["steps"]
    )
    db_session.refresh(restaurant)
    assert restaurant.restock_routing_mode == "owner_approves"
    suppliers = client.get("/api/v1/store/suppliers", headers=_auth(_token(jack))).json()
    assert len(suppliers) >= 1
    sup_id = suppliers[0]["id"]
    opening = client.post(
        "/api/v1/store/items/opening",
        headers=_auth(_token(jack)),
        json={
            "item_name": "Deep Rice",
            "quantity": 2,
            "unit": "kg",
            "zone": "Main store",
            "par_level": 20,
            "low_stock_threshold": 6,
            "default_supplier_id": sup_id,
            "yield_fraction": 1,
        },
    )
    assert opening.status_code == 201, opening.text
    inbox = client.get("/api/v1/store/approval-inbox", headers=_auth(_token(jack))).json()
    waiting = [p for p in inbox.get("pending") or [] if "Waiting on" in (p.get("approval_card_title") or "")]
    assert waiting, inbox
    assert any(p.get("kind") == "restock" for p in waiting)
    owner_inbox = client.get("/api/v1/store/approval-inbox", headers=_auth(_token(owner))).json()
    needs = [p for p in owner_inbox.get("pending") or [] if p.get("approval_needs_you")]
    assert needs, owner_inbox