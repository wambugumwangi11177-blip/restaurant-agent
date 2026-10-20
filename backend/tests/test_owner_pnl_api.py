"""
S3.2 — the P&L on the owner's screens: GET /owner/money/pnl, Home's money.pnl block, the monthly report's P&L section.
One shaper (owner/money/view.py) feeds all three, so they must agree; money crosses the edge as KES, in owner words.
"""
import re
from datetime import datetime, timedelta

import pytest

import auth
import models
from tests.fixtures import golden_restaurant as gr
from time_utils import eat_date, utcnow

API = "/api/v1/owner"


def _h(user):
    return {"Authorization": f"Bearer {auth.create_access_token({'sub': user.email, 'ver': 0})}"}


def _fresh(db, suffix, staff_role=models.StaffRole.OWNER):
    t = models.Tenant(name=f"T{suffix}")
    db.add(t)
    db.flush()
    r = models.Restaurant(tenant_id=t.id, name=f"R{suffix}", address="x")
    db.add(r)
    u = models.User(tenant_id=t.id, email=f"{suffix}@pnl.test", hashed_password=auth.get_password_hash("x"), role=models.Role.STAFF,
                    staff_role=staff_role, token_version=0)
    db.add(u)
    db.commit()
    return r, u


def _walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield path, k, v
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")


def _clockless(node):
    if isinstance(node, dict):
        return {k: _clockless(v) for k, v in node.items() if k not in ("as_of", "generated_at")}
    if isinstance(node, list):
        return [_clockless(v) for v in node]
    return node


@pytest.fixture
def month(db_session):
    """The §7 #13 month, seeded in the month of the real clock: KES 412,000 sales, 131,800 ingredients, 103,000 wages, 112,000 other."""
    g = gr.build_skeleton(db_session)
    gr.seed_pnl_month(db_session, g)
    return g


def _pnl(client, g, **params):
    return client.get(f"{API}/money/pnl", params=params, headers=_h(g.owner))


def test_the_monthly_pnl_is_the_worked_example_in_shillings_and_owner_words(client, month):
    body = _pnl(client, month).json()
    lines = {l["key"]: l for l in body["lines"]}
    assert [l["key"] for l in body["lines"]] == ["sales", "ingredients", "left_after_ingredients", "wages", "other_costs", "kept"]
    assert [l["label"] for l in body["lines"]] == ["Sales", "Ingredients", "Left after ingredients", "Wages", "Other costs", "What you kept"]
    assert (lines["sales"]["kes"], lines["ingredients"]["kes"], lines["left_after_ingredients"]["kes"]) == (412_000.0, -131_800.0, 280_200.0)
    assert (lines["wages"]["kes"], lines["other_costs"]["kes"], lines["kept"]["kes"]) == (-103_000.0, -112_000.0, 65_200.0)
    assert body["out_of_every_100"] == {"ingredients": 32.0, "wages": 25.0, "other_costs": 27.2, "kept": 15.8}
    assert body["ratios"]["prime_cost_pct"] == 57.0
    assert body["state"] == "as_entered" and body["entered_up_to"] and body["complete"] is True
    assert body["basis"] == {"ingredients": "recipe", "wages": "shifts", "delivery_commission": "none"}
    assert any("shift records" in n for n in body["notes"])
    assert {s["key"] for s in body["sections"]} == {"premises", "utilities", "operations", "marketing", "licences"}
    assert sum(s["kes"] for s in body["sections"]) == 112_000.0
    rent = next(l for s in body["sections"] for l in s["lines"] if l["key"] == "premises")
    assert (rent["name"], rent["kes"], rent["is_fixed"]) == ("Rent & premises", 60_000.0, True)
    assert body["sales_split"] == {"food": 412_000.0, "drinks": 0.0, "other": 0.0}
    assert body["period"]["kind"] == "month" and str(eat_date(utcnow()).year) in body["period"]["label"]


def test_no_cents_and_no_system_words_reach_the_owner(client, month):
    body = _pnl(client, month).json()
    assert [f"{p}.{k}" for p, k, _v in _walk(body) if "cents" in k] == []
    text = " ".join(str(v) for _p, k, v in _walk(body) if k in ("label", "name", "reason", "why") or (k == "notes" and isinstance(v, list)) or isinstance(v, str))
    for word in ("COGS", "gross profit", "operating profit", "net before tax", "opex", "cost of sales"):
        assert word.lower() not in text.lower(), word


@pytest.mark.parametrize("period", ["day", "week", "month", "year"])
def test_every_period_answers_and_a_date_picks_the_period(client, month, period):
    assert _pnl(client, month, period=period).status_code == 200
    got = _pnl(client, month, period=period, on="2026-02-10").json()
    expected = {"day": ("2026-02-10", "2026-02-10"), "week": ("2026-02-09", "2026-02-15"), "month": ("2026-02-01", "2026-02-28"), "year": ("2026-01-01", "2026-12-31")}[period]
    assert (got["period"]["start"], got["period"]["end"]) == expected
    assert got["period"]["partial"] is False if period != "year" else True


def test_bad_parameters_are_422(client, month):
    assert _pnl(client, month, period="fortnight").status_code == 422
    assert _pnl(client, month, on="not-a-date").status_code == 422


def test_a_restaurant_with_sales_but_no_costs_is_asked_for_them_not_shown_a_profit(client, db_session):
    g = gr.build_skeleton(db_session)
    pilau = g.items["Pilau"]
    gr.add_order(db_session, g, [(pilau, 4, pilau.price)], utcnow() - timedelta(minutes=30))
    db_session.commit()
    body = _pnl(client, g).json()
    assert body["state"] == "no_data" and "Enter your rent" in body["reason"]
    assert next(l for l in body["lines"] if l["key"] == "sales")["kes"] == 4 * pilau.price / 100          # what is known is shown
    assert body["complete"] is False and body["entered_up_to"] is None if "entered_up_to" in body else True


def test_a_fresh_restaurant_says_nothing_is_recorded(client, db_session):
    _r, u = _fresh(db_session, "fresh")
    body = client.get(f"{API}/money/pnl", headers=_h(u)).json()
    assert body["state"] == "no_data" and body["reason"] == "Nothing recorded in this period yet."
    assert all(l["kes"] == 0 for l in body["lines"]) and body["out_of_every_100"]["kept"] is None


def test_entering_and_voiding_an_expense_moves_the_pnl(client, month):
    before = _pnl(client, month).json()
    created = client.post(f"{API}/money/expenses", headers=_h(month.owner), json={"category": "repairs", "amount_kes": 8_500.5}).json()
    after = _pnl(client, month).json()
    assert next(l for l in after["lines"] if l["key"] == "other_costs")["kes"] == next(l for l in before["lines"] if l["key"] == "other_costs")["kes"] - 8_500.5
    assert next(l for l in after["lines"] if l["key"] == "kept")["kes"] == round(65_200.0 - 8_500.5, 2)
    client.request("DELETE", f"{API}/money/expenses/{created['id']}", headers=_h(month.owner), json={"reason": "entered twice"})
    assert _clockless(_pnl(client, month).json()) == _clockless(before)


def test_home_and_the_monthly_report_carry_the_same_block(client, month):
    api = _pnl(client, month).json()
    home = client.get(f"{API}/home", headers=_h(month.owner)).json()["areas"]["money"]["blocks"]["pnl"]
    report = next(s for s in client.get(f"{API}/report/monthly", headers=_h(month.owner)).json()["sections"] if s["key"] == "pnl")
    assert _clockless(home) == _clockless(api)
    assert _clockless({k: v for k, v in report.items() if k not in ("key", "title", "window", "rows")}) == _clockless(api)    # a report section also says which days it covers
    assert client.get(f"{API}/area/money", headers=_h(month.owner)).json()["blocks"]["pnl"]["lines"] == api["lines"]


def test_the_owners_targets_are_shown_as_the_rule_used(client, month):
    from owner.settings import FIELDS
    body = _pnl(client, month).json()
    keys = {f.key for f in FIELDS}
    assert {a["setting"] for a in body["assumptions"]} == {"food_cost_target_pct", "prime_cost_target_pct", "labour_target_pct"} <= keys


def test_entered_commissions_replace_the_estimate_through_the_api(client, db_session):
    g = gr.build_skeleton(db_session)
    burger = g.items["Burger"]
    gr.add_order(db_session, g, [(burger, 1, 60_000)], utcnow() - timedelta(minutes=30), channel=models.DeliveryChannel.GLOVO, payment=models.PaymentMethod.CARD)
    db_session.commit()
    body = _pnl(client, g).json()
    assert body["delivery_commission"] == {"kes": 150.0, "basis": "estimated"}
    assert any("estimated" in n for n in body["notes"])
    client.post(f"{API}/money/expenses", headers=_h(g.owner), json={"category": "delivery_commissions", "amount_kes": 140})
    assert _pnl(client, g).json()["delivery_commission"] == {"kes": 140.0, "basis": "entered"}


# ── who and whose ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("role,status", [(models.StaffRole.OWNER, 200), (models.StaffRole.MANAGER, 200), (models.StaffRole.CONTROLLER, 200),
                                         (models.StaffRole.SUPERVISOR, 403), (models.StaffRole.STOCKKEEPER, 403), (models.StaffRole.KITCHEN, 403),
                                         (models.StaffRole.WAITER, 403)])
def test_the_pnl_is_for_the_owner_the_manager_and_the_accountant(client, db_session, role, status):
    _r, u = _fresh(db_session, f"r{role.value}", role)
    assert client.get(f"{API}/money/pnl", headers=_h(u)).status_code == status


def test_anonymous_is_401_and_another_tenants_costs_never_leak(client, db_session, month):
    assert client.get(f"{API}/money/pnl").status_code == 401
    _r, other = _fresh(db_session, "other")
    body = client.get(f"{API}/money/pnl", headers=_h(other)).json()
    assert body["state"] == "no_data" and all(l["kes"] == 0 for l in body["lines"]) and body["sections"] == []


def test_the_pnl_is_inside_the_observer_mode_boundary():
    from observer_mode import is_blocked_request
    assert is_blocked_request("GET", "/api/v1/owner/money/pnl")
