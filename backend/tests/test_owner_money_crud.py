"""
S3.1 — expenses, recurring bills and licences (docs/v2/SPEC.md §4 P3): models, migration 052, and
/api/v1/owner/money/{categories,expenses,bills,licences}.

What this pins:
  * money is integer cents in the database and a decimal KES amount at the API: at most two places, > 0, bounded —
    0.1 + 0.2 can never reach a ledger;
  * an expense is dated by a Nairobi calendar day (`paid_on`), cannot be far in the future or the distant past;
  * nothing is deleted: an expense is voided (who, when, why) and leaves lists and totals; bills and licences are switched off;
  * bills carry a due rule (monthly day / weekly weekday / yearly month+day) with month-end clamping; paying a bill records
    an expense linked to it;
  * licences carry how long is left and a status against the owner's `licence_warning_days`;
  * owners, managers and controllers (the accountant) may use it; every other role gets 403, anonymous 401;
  * everything is scoped to the caller's own tenant and active restaurant — another tenant's id is a 404;
  * migration 052 is additive, idempotent (create_all runs first in production), reversible, renders valid PostgreSQL DDL.
"""
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa

import auth
import models
from time_utils import eat_date, utcnow

BACKEND = Path(__file__).resolve().parents[1]
API = "/api/v1/owner/money"
STANDARD_COUNT = 19


# ── helpers ───────────────────────────────────────────────────────────────────

def _tenant(db, suffix, *, staff_role=models.StaffRole.OWNER, role=models.Role.STAFF, restaurants=1):
    tenant = models.Tenant(name=f"Tenant {suffix}")
    db.add(tenant)
    db.flush()
    rests = []
    for n in range(restaurants):
        r = models.Restaurant(tenant_id=tenant.id, name=f"R{suffix}{n}", address="x")
        db.add(r)
        rests.append(r)
    user = models.User(tenant_id=tenant.id, email=f"u{suffix}@e.com", hashed_password=auth.get_password_hash("x"),
                       role=role, staff_role=staff_role, token_version=0)
    db.add(user)
    db.commit()
    token = auth.create_access_token({"sub": user.email, "ver": 0})
    return tenant, rests, user, {"Authorization": f"Bearer {token}"}


def _today():
    return eat_date(utcnow())


def _expense(client, headers, **over):
    body = {"category": "gas", "amount_kes": 4200, **over}
    return client.post(f"{API}/expenses", headers=headers, json=body)


# ═════════════════════════════════════════════════════════════════════════════
# Categories
# ═════════════════════════════════════════════════════════════════════════════

def test_the_kenyan_pnl_lines_are_there_on_first_use_and_never_duplicated(client, db_session):
    _t, (r,), _u, h = _tenant(db_session, "a")
    assert db_session.query(models.ExpenseCategory).count() == 0                # reading is lazy: nothing until used
    first = client.get(f"{API}/categories", headers=h).json()["categories"]
    again = client.get(f"{API}/categories", headers=h).json()["categories"]
    assert len(first) == STANDARD_COUNT and first == again
    assert db_session.query(models.ExpenseCategory).filter_by(restaurant_id=r.id).count() == STANDARD_COUNT
    keys = {c["key"] for c in first}
    for expected in ("premises", "kplc", "water", "garbage", "security", "gas", "charcoal", "delivery_commissions", "mpesa_charges",
                     "pos_internet", "licences", "repairs", "cleaning", "packaging", "marketing", "salaries", "casuals", "staff_meals"):
        assert expected in keys, expected
    assert all(c["name"] and c["pnl_line"] and isinstance(c["is_fixed"], bool) for c in first)
    assert {c["pnl_line"] for c in first} <= {"premises", "utilities", "staff", "fees", "operations", "marketing", "licences"}
    rent = next(c for c in first if c["key"] == "premises")
    assert rent["name"] == "Rent & premises" and rent["is_fixed"] is True
    assert next(c for c in first if c["key"] == "gas")["is_fixed"] is False


def test_a_custom_category_is_the_owners_own_and_stands_beside_the_standard_ones(client, db_session):
    _t, _r, _u, h = _tenant(db_session, "a")
    created = client.post(f"{API}/categories", headers=h, json={"name": "Live music", "pnl_line": "marketing", "is_fixed": False})
    assert created.status_code == 201
    body = created.json()
    assert body["key"] == "live-music" and body["is_standard"] is False and body["is_active"] is True
    assert client.post(f"{API}/categories", headers=h, json={"name": "live MUSIC", "pnl_line": "marketing"}).status_code == 409      # same name
    assert client.post(f"{API}/categories", headers=h, json={"name": "Gas", "pnl_line": "utilities"}).status_code == 409             # clashes with a standard one
    assert client.post(f"{API}/categories", headers=h, json={"name": "X", "pnl_line": "nonsense"}).status_code == 422
    assert client.post(f"{API}/categories", headers=h, json={"name": "  ", "pnl_line": "other"}).status_code == 422
    assert len(client.get(f"{API}/categories", headers=h).json()["categories"]) == STANDARD_COUNT + 1
    assert _expense(client, h, category="live-music", amount_kes=15000).status_code == 201


def test_a_category_can_be_switched_off_and_old_expenses_keep_it(client, db_session):
    _t, _r, _u, h = _tenant(db_session, "a")
    exp = _expense(client, h, category="charcoal").json()
    cats = {c["key"]: c for c in client.get(f"{API}/categories", headers=h).json()["categories"]}
    res = client.patch(f"{API}/categories/{cats['charcoal']['id']}", headers=h, json={"is_active": False})
    assert res.status_code == 200 and res.json()["is_active"] is False
    assert _expense(client, h, category="charcoal").status_code == 422                       # no new entries against it
    assert client.get(f"{API}/expenses/{exp['id']}", headers=h).json()["category"]["key"] == "charcoal"
    visible = client.get(f"{API}/categories", headers=h).json()["categories"]
    assert "charcoal" not in {c["key"] for c in visible}
    assert "charcoal" in {c["key"] for c in client.get(f"{API}/categories?include_inactive=true", headers=h).json()["categories"]}


# ═════════════════════════════════════════════════════════════════════════════
# Expenses
# ═════════════════════════════════════════════════════════════════════════════

def test_an_expense_is_stored_in_cents_and_shown_in_shillings(client, db_session):
    _t, (r,), user, h = _tenant(db_session, "a")
    res = _expense(client, h, amount_kes=1234.5, supplier="Total Gas", note="Two 13 kg cylinders", method="mpesa", receipt_ref="receipts/2026/10/a1.jpg")
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["amount_kes"] == 1234.5 and "amount_cents" not in body
    assert (body["category"]["key"], body["method"], body["supplier"], body["receipt_ref"]) == ("gas", "mpesa", "Total Gas", "receipts/2026/10/a1.jpg")
    assert body["paid_on"] == _today().isoformat() and body["paid_by"]["id"] == user.id
    row = db_session.query(models.Expense).one()
    assert row.amount_cents == 123_450 and isinstance(row.amount_cents, int) and row.restaurant_id == r.id and row.paid_by_user_id == user.id


@pytest.mark.parametrize("sent,cents", [(19.99, 1999), (0.1, 10), (0.01, 1), (1e3, 100_000), ("250", 25_000), ("70000.00", 7_000_000), (100_000_000, 10_000_000_000)])
def test_decimal_amounts_land_on_the_exact_cent(client, db_session, sent, cents):
    _t, _r, _u, h = _tenant(db_session, "a")
    assert _expense(client, h, amount_kes=sent).status_code == 201
    assert db_session.query(models.Expense).one().amount_cents == cents


@pytest.mark.parametrize("bad", [0, -5, 0.001, 12.345, 100_000_001, "abc", None, "NaN", "Infinity", True])
def test_amounts_that_are_not_money_are_refused(client, db_session, bad):
    _t, _r, _u, h = _tenant(db_session, "a")
    assert _expense(client, h, amount_kes=bad).status_code == 422
    assert db_session.query(models.Expense).count() == 0


def test_the_date_is_a_nairobi_day_and_cannot_be_far_in_the_future_or_the_past(client, db_session):
    _t, _r, _u, h = _tenant(db_session, "a")
    today = _today()
    assert _expense(client, h, paid_on=(today + timedelta(days=1)).isoformat()).status_code == 201          # tomorrow is allowed
    assert _expense(client, h, paid_on=(today + timedelta(days=2)).isoformat()).status_code == 422
    assert _expense(client, h, paid_on=(today - timedelta(days=365 * 5 - 2)).isoformat()).status_code == 201
    assert _expense(client, h, paid_on=(today - timedelta(days=365 * 5 + 40)).isoformat()).status_code == 422
    assert _expense(client, h, paid_on="not-a-date").status_code == 422


def test_unknown_fields_methods_and_categories_are_refused(client, db_session):
    _t, _r, _u, h = _tenant(db_session, "a")
    assert _expense(client, h, method="barter").status_code == 422
    assert _expense(client, h, category="nope").status_code == 422
    assert _expense(client, h, amount_cents=5).status_code == 422                       # cents never cross the API
    assert _expense(client, h, restaurant_id=99).status_code == 422                     # there is no id to forge
    assert _expense(client, h, note="x" * 501).status_code == 422
    assert _expense(client, h, supplier="x" * 121).status_code == 422
    assert client.post(f"{API}/expenses", headers=h, json={"amount_kes": 5}).status_code == 422


def test_listing_filters_orders_and_totals(client, db_session):
    _t, _r, _u, h = _tenant(db_session, "a")
    today = _today()
    for days_ago, cat, amount in ((0, "gas", 4200), (1, "kplc", 18_000), (2, "gas", 4400), (10, "premises", 70_000), (40, "water", 3_000)):
        assert _expense(client, h, category=cat, amount_kes=amount, paid_on=(today - timedelta(days=days_ago)).isoformat()).status_code == 201
    everything = client.get(f"{API}/expenses", headers=h).json()
    assert [e["amount_kes"] for e in everything["items"]] == [4200, 18_000, 4400, 70_000, 3_000]               # newest first
    assert everything["count"] == 5 and everything["total_kes"] == 99_600
    month = client.get(f"{API}/expenses?from={(today - timedelta(days=10)).isoformat()}&to={today.isoformat()}", headers=h).json()
    assert month["count"] == 4 and month["total_kes"] == 96_600                                                  # both ends inclusive
    gas = client.get(f"{API}/expenses?category=gas", headers=h).json()
    assert gas["count"] == 2 and gas["total_kes"] == 8_600
    page = client.get(f"{API}/expenses?limit=2&offset=1", headers=h).json()
    assert [e["amount_kes"] for e in page["items"]] == [18_000, 4400] and page["count"] == 5 and page["total_kes"] == 99_600
    assert client.get(f"{API}/expenses?limit=0", headers=h).status_code == 422
    assert client.get(f"{API}/expenses?limit=501", headers=h).status_code == 422
    assert client.get(f"{API}/expenses?category=nope", headers=h).status_code == 422
    assert client.get(f"{API}/expenses?from=2026-13-40", headers=h).status_code == 422


def test_editing_an_expense_changes_only_what_was_sent(client, db_session):
    _t, _r, user, h = _tenant(db_session, "a")
    exp = _expense(client, h, supplier="Total Gas").json()
    res = client.patch(f"{API}/expenses/{exp['id']}", headers=h, json={"amount_kes": 4300.25, "category": "charcoal", "note": "corrected"})
    assert res.status_code == 200
    body = res.json()
    assert (body["amount_kes"], body["category"]["key"], body["note"], body["supplier"]) == (4300.25, "charcoal", "corrected", "Total Gas")
    assert db_session.query(models.Expense).one().amount_cents == 430_025
    assert client.patch(f"{API}/expenses/{exp['id']}", headers=h, json={}).status_code == 422
    assert client.patch(f"{API}/expenses/{exp['id']}", headers=h, json={"amount_kes": -1}).status_code == 422
    assert client.patch(f"{API}/expenses/{exp['id']}", headers=h, json={"voided_at": "2026-01-01"}).status_code == 422


def test_an_expense_is_voided_never_deleted(client, db_session):
    _t, _r, user, h = _tenant(db_session, "a")
    keep, gone = _expense(client, h, amount_kes=1000).json(), _expense(client, h, amount_kes=2500).json()
    assert client.request("DELETE", f"{API}/expenses/{gone['id']}", headers=h, json={"reason": "ab"}).status_code == 422          # a reason is required
    res = client.request("DELETE", f"{API}/expenses/{gone['id']}", headers=h, json={"reason": "Entered twice"})
    assert res.status_code == 200 and res.json()["voided"]["reason"] == "Entered twice" and res.json()["voided"]["by"]["id"] == user.id
    assert db_session.query(models.Expense).count() == 2                                                # the row is still there
    listing = client.get(f"{API}/expenses", headers=h).json()
    assert [e["id"] for e in listing["items"]] == [keep["id"]] and listing["total_kes"] == 1000
    audit = client.get(f"{API}/expenses?include_voided=true", headers=h).json()
    assert audit["count"] == 2 and {e["id"] for e in audit["items"] if e["voided"]} == {gone["id"]}
    assert client.get(f"{API}/expenses/{gone['id']}", headers=h).json()["voided"]["reason"] == "Entered twice"
    assert client.request("DELETE", f"{API}/expenses/{gone['id']}", headers=h, json={"reason": "Again"}).status_code == 409
    assert client.patch(f"{API}/expenses/{gone['id']}", headers=h, json={"note": "x"}).status_code == 409


# ═════════════════════════════════════════════════════════════════════════════
# Bills
# ═════════════════════════════════════════════════════════════════════════════

def _bill(client, h, **over):
    body = {"name": "Rent", "category": "premises", "amount_kes": 70_000, "frequency": "monthly", "due_day": 4, **over}
    return client.post(f"{API}/bills", headers=h, json=body)


def test_a_monthly_bill_has_a_due_day_and_a_next_due_date(client, db_session):
    _t, (r,), _u, h = _tenant(db_session, "a")
    res = _bill(client, h, supplier="Landlord")
    assert res.status_code == 201, res.text
    body = res.json()
    assert (body["name"], body["amount_kes"], body["frequency"], body["due_day"], body["category"]["key"]) == ("Rent", 70_000, "monthly", 4, "premises")
    today = _today()
    nxt = date.fromisoformat(body["next_due_on"])
    assert nxt.day == 4 and nxt >= today and (nxt - today).days <= 31
    assert db_session.query(models.RecurringBill).one().amount_cents == 7_000_000


@pytest.mark.parametrize("over,ok", [
    ({"due_day": 0}, False), ({"due_day": 32}, False), ({"due_day": 31}, True), ({"due_day": 1}, True),
    ({"frequency": "weekly", "due_day": 7}, False), ({"frequency": "weekly", "due_day": 0}, True), ({"frequency": "weekly", "due_day": 6}, True),
    ({"frequency": "yearly", "due_day": 15}, False), ({"frequency": "yearly", "due_day": 15, "due_month": 13}, False),
    ({"frequency": "yearly", "due_day": 15, "due_month": 6}, True), ({"frequency": "daily"}, False),
    ({"end_on": "2020-01-01", "start_on": "2021-01-01"}, False), ({"amount_kes": 0}, False), ({"name": " "}, False),
    ({"due_month": 6}, False),                                                           # a month only makes sense for yearly bills
])
def test_a_due_rule_must_make_sense(client, db_session, over, ok):
    _t, _r, _u, h = _tenant(db_session, "a")
    assert (_bill(client, h, **over).status_code == 201) is ok


def test_next_due_clamps_to_the_end_of_short_months_and_leap_years():
    from owner.money.bills import next_due
    bill = lambda **kw: models.RecurringBill(frequency="monthly", due_day=31, start_on=date(2020, 1, 1), **kw)   # noqa: E731
    assert next_due(bill(), date(2026, 4, 10)) == date(2026, 4, 30)                     # April has 30 days
    assert next_due(bill(), date(2026, 4, 30)) == date(2026, 4, 30)                     # due today is still next
    assert next_due(bill(), date(2026, 5, 1)) == date(2026, 5, 31)
    assert next_due(bill(), date(2026, 2, 1)) == date(2026, 2, 28)
    assert next_due(bill(), date(2028, 2, 1)) == date(2028, 2, 29)
    weekly = models.RecurringBill(frequency="weekly", due_day=2, start_on=date(2020, 1, 1))                           # Wednesday
    assert next_due(weekly, date(2026, 10, 14)) == date(2026, 10, 14)                   # 2026-10-14 is a Wednesday
    assert next_due(weekly, date(2026, 10, 15)) == date(2026, 10, 21)
    yearly = models.RecurringBill(frequency="yearly", due_day=29, due_month=2, start_on=date(2020, 1, 1))
    assert next_due(yearly, date(2026, 3, 1)) == date(2027, 2, 28)
    assert next_due(yearly, date(2027, 3, 1)) == date(2028, 2, 29)
    ended = models.RecurringBill(frequency="monthly", due_day=4, start_on=date(2020, 1, 1), end_on=date(2026, 6, 30))
    assert next_due(ended, date(2026, 10, 1)) is None
    future = models.RecurringBill(frequency="monthly", due_day=4, start_on=date(2027, 1, 20))
    assert next_due(future, date(2026, 10, 1)) == date(2027, 2, 4)                      # not before it starts


def test_paying_a_bill_records_an_expense_linked_to_it(client, db_session):
    _t, _r, user, h = _tenant(db_session, "a")
    bill = _bill(client, h).json()
    paid = client.post(f"{API}/bills/{bill['id']}/pay", headers=h, json={"method": "bank"})
    assert paid.status_code == 201, paid.text
    exp = paid.json()
    assert (exp["amount_kes"], exp["category"]["key"], exp["method"], exp["bill_id"], exp["supplier"]) == (70_000, "premises", "bank", bill["id"], "")
    assert exp["paid_on"] == _today().isoformat() and exp["paid_by"]["id"] == user.id
    other = client.post(f"{API}/bills/{bill['id']}/pay", headers=h, json={"amount_kes": 68_500.5, "paid_on": (_today() - timedelta(days=3)).isoformat()})
    assert other.json()["amount_kes"] == 68_500.5 and other.json()["method"] == "cash"
    listed = client.get(f"{API}/expenses", headers=h).json()
    assert listed["count"] == 2 and {e["bill_id"] for e in listed["items"]} == {bill["id"]}
    assert client.post(f"{API}/bills/{bill['id']}/pay", headers=h, json={"amount_kes": 0}).status_code == 422
    client.patch(f"{API}/bills/{bill['id']}", headers=h, json={"is_active": False})
    assert client.post(f"{API}/bills/{bill['id']}/pay", headers=h, json={}).status_code == 409                # a bill that is off cannot be paid


def test_bills_can_be_edited_and_switched_off(client, db_session):
    _t, _r, _u, h = _tenant(db_session, "a")
    a, b = _bill(client, h).json(), _bill(client, h, name="KPLC", category="kplc", amount_kes=18_000, due_day=20).json()
    res = client.patch(f"{API}/bills/{b['id']}", headers=h, json={"amount_kes": 19_250, "due_day": 22})
    assert res.status_code == 200 and (res.json()["amount_kes"], res.json()["due_day"]) == (19_250, 22)
    assert client.patch(f"{API}/bills/{b['id']}", headers=h, json={"due_day": 40}).status_code == 422
    assert client.patch(f"{API}/bills/{b['id']}", headers=h, json={"frequency": "weekly"}).status_code == 422       # the rule stays consistent: day 22 is not a weekday
    client.patch(f"{API}/bills/{a['id']}", headers=h, json={"is_active": False})
    assert [x["name"] for x in client.get(f"{API}/bills", headers=h).json()["bills"]] == ["KPLC"]
    assert {x["name"] for x in client.get(f"{API}/bills?include_inactive=true", headers=h).json()["bills"]} == {"Rent", "KPLC"}
    assert db_session.query(models.RecurringBill).count() == 2


def test_bills_come_back_in_the_order_they_fall_due(client, db_session):
    _t, _r, _u, h = _tenant(db_session, "a")
    for name, day in (("C", 28), ("A", 3), ("B", 15)):
        _bill(client, h, name=name, due_day=day)
    bills = client.get(f"{API}/bills", headers=h).json()["bills"]
    dues = [b["next_due_on"] for b in bills]
    assert dues == sorted(dues) and len(bills) == 3


# ═════════════════════════════════════════════════════════════════════════════
# Licences
# ═════════════════════════════════════════════════════════════════════════════

def _licence(client, h, name="Single business permit", days=90, **over):
    body = {"name": name, "issuer": "Nairobi County", "expires_on": (_today() + timedelta(days=days)).isoformat(), **over}
    return client.post(f"{API}/licences", headers=h, json=body)


def test_a_licence_says_how_long_is_left_and_what_that_means(client, db_session):
    _t, _r, _u, h = _tenant(db_session, "a")
    for name, days in (("Health certificate", 10), ("Fire certificate", -3), ("Single business permit", 200), ("Music licence", 14), ("Liquor licence", 15)):
        assert _licence(client, h, name, days, cost_kes=12_500 if name == "Liquor licence" else None).status_code == 201
    items = client.get(f"{API}/licences", headers=h).json()["licences"]
    assert [(i["name"], i["days_left"], i["status"]) for i in items] == [
        ("Fire certificate", -3, "expired"), ("Health certificate", 10, "expiring"), ("Music licence", 14, "expiring"),
        ("Liquor licence", 15, "ok"), ("Single business permit", 200, "ok")]                      # soonest first; 14 days is the default warning
    assert next(i for i in items if i["name"] == "Liquor licence")["cost_kes"] == 12_500
    assert next(i for i in items if i["name"] == "Fire certificate")["cost_kes"] is None


def test_the_owners_warning_days_decide_expiring(client, db_session):
    from owner.settings import update_settings
    _t, (r,), user, h = _tenant(db_session, "a")
    _licence(client, h, "Health certificate", 20)
    assert client.get(f"{API}/licences", headers=h).json()["licences"][0]["status"] == "ok"
    update_settings(db_session, r.id, user.id, {"licence_warning_days": 30})
    assert client.get(f"{API}/licences", headers=h).json()["licences"][0]["status"] == "expiring"


def test_licences_can_be_edited_renewed_and_switched_off(client, db_session):
    _t, _r, _u, h = _tenant(db_session, "a")
    lic = _licence(client, h, days=5).json()
    renewed = client.patch(f"{API}/licences/{lic['id']}", headers=h, json={"expires_on": (_today() + timedelta(days=365)).isoformat(), "cost_kes": 9000.5, "document_ref": "docs/permit-2027.pdf"})
    assert renewed.status_code == 200 and renewed.json()["status"] == "ok" and renewed.json()["cost_kes"] == 9000.5
    assert db_session.query(models.Licence).one().cost_cents == 900_050
    assert client.patch(f"{API}/licences/{lic['id']}", headers=h, json={"expires_on": "soon"}).status_code == 422
    assert client.patch(f"{API}/licences/{lic['id']}", headers=h, json={"cost_kes": -1}).status_code == 422
    client.patch(f"{API}/licences/{lic['id']}", headers=h, json={"is_active": False})
    assert client.get(f"{API}/licences", headers=h).json()["licences"] == []
    assert len(client.get(f"{API}/licences?include_inactive=true", headers=h).json()["licences"]) == 1
    assert _licence(client, h, name=" ").status_code == 422
    assert _licence(client, h, name="Lapsed permit", days=-400).status_code == 201              # a lapsed licence still has to be recorded
    assert client.post(f"{API}/licences", headers=h, json={"name": "Ancient", "expires_on": "1999-12-31"}).status_code == 422


# ═════════════════════════════════════════════════════════════════════════════
# Who may use it, and whose data it is
# ═════════════════════════════════════════════════════════════════════════════

def _seed_ids(client, h):
    cat = client.get(f"{API}/categories", headers=h).json()["categories"][0]["id"]
    exp = _expense(client, h).json()["id"]
    bill = _bill(client, h).json()["id"]
    lic = _licence(client, h).json()["id"]
    return {"cat": cat, "exp": exp, "bill": bill, "lic": lic}


def _requests(ids):
    return [
        ("GET", "/categories", None), ("POST", "/categories", {"name": "Zzz", "pnl_line": "other"}), ("PATCH", f"/categories/{ids['cat']}", {"name": "Renamed"}),
        ("GET", "/expenses", None), ("POST", "/expenses", {"category": "gas", "amount_kes": 10}), ("GET", f"/expenses/{ids['exp']}", None),
        ("PATCH", f"/expenses/{ids['exp']}", {"note": "x"}), ("DELETE", f"/expenses/{ids['exp']}", {"reason": "mistake"}),
        ("GET", "/bills", None), ("POST", "/bills", {"name": "B", "category": "gas", "amount_kes": 1, "frequency": "monthly", "due_day": 1}),
        ("PATCH", f"/bills/{ids['bill']}", {"note": "x"}), ("POST", f"/bills/{ids['bill']}/pay", {}),
        ("GET", "/licences", None), ("POST", "/licences", {"name": "L", "expires_on": "2030-01-01"}), ("PATCH", f"/licences/{ids['lic']}", {"note": "x"}),
    ]


@pytest.mark.parametrize("staff_role", [models.StaffRole.SUPERVISOR, models.StaffRole.STOCKKEEPER, models.StaffRole.KITCHEN, models.StaffRole.WAITER])
def test_other_staff_roles_cannot_touch_the_ledger(client, db_session, staff_role):
    _t, _r, _owner, owner_h = _tenant(db_session, "own")
    ids = _seed_ids(client, owner_h)
    _t2, _r2, _u, h = _tenant(db_session, f"s{staff_role.value}", staff_role=staff_role)
    for method, path, body in _requests(ids):
        assert client.request(method, f"{API}{path}", headers=h, json=body).status_code == 403, (staff_role, method, path)
    assert db_session.query(models.Expense).count() == 1 and db_session.query(models.RecurringBill).count() == 1


@pytest.mark.parametrize("staff_role", [models.StaffRole.OWNER, models.StaffRole.MANAGER, models.StaffRole.CONTROLLER])
def test_owner_manager_and_controller_the_accountant_may(client, db_session, staff_role):
    _t, _r, _u, h = _tenant(db_session, f"s{staff_role.value}", staff_role=staff_role)
    assert client.get(f"{API}/categories", headers=h).status_code == 200
    assert _expense(client, h).status_code == 201
    assert _bill(client, h).status_code == 201
    assert _licence(client, h).status_code == 201


def test_admin_accounts_pass_like_owners_and_unassigned_staff_are_told_so(client, db_session):
    _t, _r, _u, h = _tenant(db_session, "admin", staff_role=None, role=models.Role.ADMIN)
    assert client.get(f"{API}/expenses", headers=h).status_code == 200
    _t2, _r2, _u2, h2 = _tenant(db_session, "none", staff_role=None)
    res = client.get(f"{API}/expenses", headers=h2)
    assert res.status_code == 403 and res.json()["detail"] == "staff_role_unassigned"


def test_anonymous_callers_are_401(client, db_session):
    _t, _r, _u, h = _tenant(db_session, "a")
    for method, path, body in _requests(_seed_ids(client, h)):
        assert client.request(method, f"{API}{path}", json=body).status_code == 401, (method, path)


def test_another_tenants_ids_are_404_and_its_rows_never_appear(client, db_session):
    _ta, _ra, _ua, ha = _tenant(db_session, "a")
    _tb, _rb, _ub, hb = _tenant(db_session, "b")
    ids = _seed_ids(client, ha)
    _expense(client, hb, amount_kes=77)
    for method, path, body in _requests(ids):
        if any(x in path for x in (f"/{ids['exp']}", f"/{ids['bill']}", f"/{ids['lic']}", f"/{ids['cat']}")):
            assert client.request(method, f"{API}{path}", headers=hb, json=body).status_code == 404, (method, path)
    mine = client.get(f"{API}/expenses", headers=hb).json()
    assert [e["amount_kes"] for e in mine["items"]] == [77] and mine["total_kes"] == 77
    assert client.get(f"{API}/bills", headers=hb).json()["bills"] == []
    assert client.get(f"{API}/licences", headers=hb).json()["licences"] == []
    assert db_session.query(models.Expense).filter_by(id=ids["exp"]).one().voided_at is None          # A's expense survived B's attempt to void it
    assert db_session.query(models.ExpenseCategory).filter_by(id=ids["cat"]).one().name != "Renamed"


def test_categories_are_per_restaurant_so_a_category_key_from_elsewhere_means_nothing(client, db_session):
    _ta, _ra, _ua, ha = _tenant(db_session, "a")
    _tb, _rb, _ub, hb = _tenant(db_session, "b")
    client.post(f"{API}/categories", headers=ha, json={"name": "Live music", "pnl_line": "marketing"})
    assert _expense(client, hb, category="live-music").status_code == 422
    assert _expense(client, ha, category="live-music").status_code == 201


def test_forging_the_active_restaurant_does_not_cross_the_tenant_boundary(client, db_session):
    _ta, (ra,), _ua, ha = _tenant(db_session, "a")
    _tb, (rb,), ub, hb = _tenant(db_session, "b")
    _expense(client, ha, amount_kes=500)
    ub.active_restaurant_id = ra.id
    db_session.commit()
    assert client.get(f"{API}/expenses", headers=hb).json()["count"] == 0
    assert _expense(client, hb, amount_kes=900).status_code == 201
    assert {e.restaurant_id: e.amount_cents for e in db_session.query(models.Expense)} == {ra.id: 50_000, rb.id: 90_000}


def test_each_branch_of_a_chain_has_its_own_ledger(client, db_session):
    _t, (r1, r2), user, h = _tenant(db_session, "chain", restaurants=2)
    user.active_restaurant_id = r1.id
    db_session.commit()
    _expense(client, h, amount_kes=100)
    user.active_restaurant_id = r2.id
    db_session.commit()
    assert client.get(f"{API}/expenses", headers=h).json()["count"] == 0
    _expense(client, h, amount_kes=250)
    assert {e.restaurant_id: e.amount_cents for e in db_session.query(models.Expense)} == {r1.id: 10_000, r2.id: 25_000}
    assert db_session.query(models.ExpenseCategory).filter(models.ExpenseCategory.restaurant_id.in_([r1.id, r2.id])).count() == 2 * STANDARD_COUNT


def test_the_money_api_is_inside_the_observer_mode_boundary():
    from observer_mode import is_blocked_request
    for method, path in (("GET", "/api/v1/owner/money/expenses"), ("POST", "/api/v1/owner/money/expenses"), ("POST", "/api/v1/owner/money/bills/1/pay")):
        assert is_blocked_request(method, path), path


def test_a_failed_request_leaves_no_half_written_rows(client, db_session):
    _t, _r, _u, h = _tenant(db_session, "a")
    assert _expense(client, h, amount_kes=-1).status_code == 422
    assert _bill(client, h, due_day=99).status_code == 422
    assert db_session.query(models.Expense).count() == db_session.query(models.RecurringBill).count() == 0


# ═════════════════════════════════════════════════════════════════════════════
# Migration 052
# ═════════════════════════════════════════════════════════════════════════════

TABLES = ("expense_categories", "expenses", "recurring_bills", "licences")


def _load_migration():
    import importlib.util
    path = BACKEND / "alembic" / "versions" / "052_add_money_ledger.py"
    spec = importlib.util.spec_from_file_location("migration_052", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_migration(connection, fn_name):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    module = _load_migration()
    with Operations.context(MigrationContext.configure(connection)):
        getattr(module, fn_name)()


def test_migration_052_follows_051_and_alembic_has_one_head():
    module = _load_migration()
    assert module.down_revision == "051_restaurant_settings"
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    assert ScriptDirectory.from_config(config).get_heads() == [module.revision]


def test_migration_052_creates_exactly_the_model_columns_and_is_reversible_and_idempotent(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    models.Base.metadata.create_all(engine, tables=[
        models.Tenant.__table__, models.Restaurant.__table__, models.User.__table__, models.Supplier.__table__])
    with engine.begin() as conn:
        _run_migration(conn, "upgrade")
        inspector = sa.inspect(conn)
        assert set(TABLES) <= set(inspector.get_table_names())
        for model in (models.ExpenseCategory, models.Expense, models.RecurringBill, models.Licence):
            built = {c["name"] for c in inspector.get_columns(model.__tablename__)}
            assert built == {c.name for c in model.__table__.columns}, model.__tablename__
        _run_migration(conn, "upgrade")                                  # create_all() already ran in production: must not raise
        _run_migration(conn, "downgrade")
        assert not set(TABLES) & set(sa.inspect(conn).get_table_names())
        _run_migration(conn, "downgrade")
        _run_migration(conn, "upgrade")
        assert set(TABLES) <= set(sa.inspect(conn).get_table_names())


def test_migration_052_renders_postgresql_ddl_offline():
    env = {**os.environ, "DATABASE_URL": "postgresql+psycopg2://offline:offline@localhost:5432/offline", "SECRET_KEY": "x"}
    up = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "051_restaurant_settings:052_money_ledger", "--sql"],
                        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
    assert up.returncode == 0, up.stderr[-1500:]
    sql = up.stdout
    for table in TABLES:
        assert f"CREATE TABLE {table}" in sql, table
    assert "amount_cents INTEGER NOT NULL" in sql and "paid_on DATE NOT NULL" in sql and "REFERENCES restaurants (id) ON DELETE CASCADE" in sql
    assert "DROP" not in sql
    down = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "052_money_ledger:051_restaurant_settings", "--sql"],
                          cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
    assert down.returncode == 0, down.stderr[-1500:]
    assert all(f"DROP TABLE {t}" in down.stdout for t in TABLES)
    out = down.stdout
    assert out.index("DROP TABLE expenses") < out.index("DROP TABLE recurring_bills") < out.index("DROP TABLE expense_categories")      # children first
