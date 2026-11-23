"""Approval card labels."""
import auth
import models
from services.approval_workflow import enrich_approval_item, viewer_is_actor
from tests.test_storekeeper_foundation import _add_staff, _tenant


def test_owner_sees_needs_you(db_session):
    _, owner, _ = _tenant(db_session, "Eleven", "owner@eleven.leviii")
    item = {"kind": "waste", "status": "needs_approval", "action": "Approve write-off", "id": 1}
    item["item_name"] = "Tomatoes"
    item["quantity"] = 3
    item["unit"] = "kg"
    item["person_name"] = "Jack"
    item["created_at"] = "2026-01-01T10:00:00"
    out = enrich_approval_item(item, owner)
    assert out["approval_card_title"] == "Write-off"
    assert out["approval_needs_you"] is True
    assert any("Tomatoes" in line for line in out["approval_detail_bullets"])
    assert out["approval_viewer_is_actor"] is True


def test_storekeeper_sees_waiting(db_session):
    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner@eleven.leviii")
    jack = _add_staff(db_session, tenant, restaurant, "jack@eleven.leviii", models.StaffRole.STOCKKEEPER)
    item = {"kind": "waste", "status": "needs_approval", "action": "Approve write-off", "id": 1}
    out = enrich_approval_item(item, jack)
    assert out["approval_card_title"] == "Waiting on Owner"
    assert out["approval_viewer_is_actor"] is False
    assert viewer_is_actor(jack, "owner") is False