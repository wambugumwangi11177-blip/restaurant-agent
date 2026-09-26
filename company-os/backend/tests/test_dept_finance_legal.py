"""Departments 5 (Finance) and 6 (Legal)."""

from datetime import date, timedelta

from app.departments.legal import fill_template
from app.kernel.agents.tools import TOOLS, Effect
from app.kernel.models import Notification, Proposal
from tests.conftest import llm_turn

TODAY = date.today()


def _inv(client, h, **kw):
    body = {"title": "POS rollout", "issue_date": (TODAY - timedelta(days=40)).isoformat(),
            "due_date": (TODAY - timedelta(days=10)).isoformat(), "subtotal_minor": 10000000, "tax_minor": 1600000,
            "status": "sent", **kw}
    r = client.post("/api/v1/records/invoice", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_finance_is_founder_only_and_never_moves_money(client, make_workspace, add_member):
    w = make_workspace("acme")
    staff = add_member(w["h"], "staff", "s@acme.example.com")
    adv = add_member(w["h"], "advisor", "a@acme.example.com")
    for h in (staff, adv):
        assert client.get("/api/v1/records/invoice", headers=h).status_code == 403
        assert client.get("/api/v1/reports/finance.runway", headers=h).status_code == 403
    # No registered tool can move money: finance registers no EXTERNAL tools at all.
    finance_tools = [t for t in TOOLS.values() if t.permission.startswith("finance")]
    assert all(t.effect is not Effect.EXTERNAL for t in finance_tools)
    assert not [n for n in TOOLS if any(w_ in n for w_ in ("pay", "transfer", "refund", "withdraw"))]


def test_invoice_numbering_totals_and_payments(client, make_workspace):
    w = make_workspace("acme")
    h = w["h"]
    a = _inv(client, h)
    b = _inv(client, h)
    year = (TODAY - timedelta(days=40)).year
    assert (a["number"], b["number"]) == (f"INV-{year}-0001", f"INV-{year}-0002")
    assert a["total_minor"] == 11600000 and a["currency"] == "KES"
    assert client.post("/api/v1/records/invoice", headers=h, json={**{k: a[k] for k in ("title", "issue_date", "due_date", "subtotal_minor")}, "number": a["number"]}).status_code == 409
    bad = client.post("/api/v1/records/invoice", headers=h, json={"title": "x", "issue_date": "2026-09-10", "due_date": "2026-09-01", "subtotal_minor": 1})
    assert bad.status_code == 422

    p1 = client.post("/api/v1/records/payment", headers=h, json={"invoice_id": a["id"], "amount_minor": 6000000, "received_on": TODAY.isoformat(), "method": "mpesa", "reference": "QWE123"}).json()
    assert client.get(f"/api/v1/records/invoice/{a['id']}", headers=h).json()["status"] == "partially_paid"
    client.post("/api/v1/records/payment", headers=h, json={"invoice_id": a["id"], "amount_minor": 5600000, "received_on": TODAY.isoformat()})
    got = client.get(f"/api/v1/records/invoice/{a['id']}", headers=h).json()
    assert (got["status"], got["amount_paid_minor"]) == ("paid", 11600000)
    # Moving a payment to another invoice recomputes both.
    client.patch(f"/api/v1/records/payment/{p1['id']}", headers=h, json={"invoice_id": b["id"]})
    assert client.get(f"/api/v1/records/invoice/{a['id']}", headers=h).json()["status"] == "partially_paid"
    assert client.get(f"/api/v1/records/invoice/{b['id']}", headers=h).json()["amount_paid_minor"] == 6000000
    client.delete(f"/api/v1/records/payment/{p1['id']}", headers=h)
    assert client.get(f"/api/v1/records/invoice/{b['id']}", headers=h).json()["status"] == "sent"
    usd = client.post("/api/v1/records/payment", headers=h, json={"invoice_id": b["id"], "amount_minor": 1, "currency": "USD", "received_on": TODAY.isoformat()})
    assert usd.status_code == 422


def test_expenses_bookkeeper_suggests_but_never_confirms(client, make_workspace):
    w = make_workspace("acme")
    h = w["h"]
    assert client.post("/api/v1/records/expense", headers=h, json={"spent_on": TODAY.isoformat(), "vendor": "Safaricom", "amount_minor": 100000, "status": "confirmed"}).status_code == 422
    for _ in range(2):
        client.post("/api/v1/records/expense", headers=h, json={"spent_on": TODAY.isoformat(), "vendor": "Safaricom", "amount_minor": 100000, "category": "Internet", "status": "confirmed"})
    e = client.post("/api/v1/records/expense", headers=h, json={"spent_on": TODAY.isoformat(), "vendor": "safaricom ", "amount_minor": 120000}).json()
    client.post("/api/v1/records/expense", headers=h, json={"spent_on": TODAY.isoformat(), "vendor": "New vendor", "amount_minor": 5000})
    out = client.post("/api/v1/agents/bookkeeper/run", headers=h, json={}).json()["output"]
    assert "suggest 'Internet' (2 past)" in out and "New vendor" in out and "no history" in out
    got = client.get(f"/api/v1/records/expense/{e['id']}", headers=h).json()
    assert (got["suggested_category"], got["category"], got["status"]) == ("Internet", None, "unconfirmed")


def test_runway_and_month_reports_are_honest(client, make_workspace):
    w = make_workspace("acme")
    h = w["h"]
    r = client.get("/api/v1/reports/finance.runway", headers=h).json()
    assert "No cash snapshots recorded yet" in r["summary"]
    first_of_month = TODAY.replace(day=1)
    for months_back in (1, 2, 3):
        d = first_of_month
        for _ in range(months_back):
            d = (d - timedelta(days=1)).replace(day=1)
        client.post("/api/v1/records/expense", headers=h, json={"spent_on": d.isoformat(), "vendor": "Rent", "amount_minor": 30000000, "category": "Rent", "status": "confirmed"})
    client.post("/api/v1/records/cash_snapshot", headers=h, json={"account": "Bank", "as_of": TODAY.isoformat(), "balance_minor": 180000000})
    client.post("/api/v1/records/cash_snapshot", headers=h, json={"account": "USD account", "as_of": TODAY.isoformat(), "balance_minor": 100000, "currency": "USD"})
    r = client.get("/api/v1/reports/finance.runway", headers=h).json()
    assert "about 6.0 months of runway" in r["summary"] and "USD are NOT included" in r["summary"]
    m = client.get("/api/v1/reports/finance.month", headers=h, params={"month": "bad"})
    assert m.status_code == 422


def test_collections_proposes_reminders_to_linked_contact(client, make_workspace, db):
    w = make_workspace("acme")
    h = w["h"]
    org = client.post("/api/v1/records/organization", headers=h, json={"name": "Vibanda"}).json()
    person = client.post("/api/v1/records/person", headers=h, json={"full_name": "Accounts", "email": "accounts@vibanda.example.com"}).json()
    client.post("/api/v1/links", headers=h, json={"from_type": "person", "from_id": person["id"], "to_type": "organization", "to_id": org["id"], "relation": "works_at"})
    inv = _inv(client, h, organization_id=org["id"])
    _inv(client, h)  # overdue, no client -> reported, not proposed
    r = client.post("/api/v1/jobs/collections_check/run", headers=h).json()
    assert r["summary"] == "2 overdue, 2 not yet reminded"
    out = client.post("/api/v1/agents/collections/run", headers=h, json={}).json()["output"]
    assert "reminder to accounts@vibanda.example.com: pending_approval" in out and "no contact email" in out
    p = db.query(Proposal).one()
    assert p.args["to"] == "accounts@vibanda.example.com" and inv["number"] in p.args["subject"]
    assert client.post("/api/v1/jobs/collections_check/run", headers=h).json()["summary"] == "2 overdue, 1 not yet reminded"


def test_unmatched_payments_suggest_exact_matches_only(client, make_workspace):
    w = make_workspace("acme")
    inv = _inv(client, w["h"])
    client.post("/api/v1/records/payment", headers=w["h"], json={"amount_minor": 11600000, "received_on": TODAY.isoformat(), "reference": "MPESA1"})
    client.post("/api/v1/records/payment", headers=w["h"], json={"amount_minor": 999, "received_on": TODAY.isoformat()})
    rows = client.get("/api/v1/reports/finance.unmatched", headers=w["h"]).json()["rows"]
    assert rows[0][4] == inv["number"] and rows[1][4] == "no exact match"


# ── Legal ────────────────────────────────────────────────────────────────────

def test_contract_deadlines_and_job(client, make_workspace, db):
    w = make_workspace("acme")
    h = w["h"]
    end = TODAY + timedelta(days=40)
    c = client.post("/api/v1/records/contract", headers=h, json={"title": "Vibanda MSA", "kind": "msa", "status": "signed", "end_on": end.isoformat(), "notice_days": 30, "auto_renews": True}).json()
    client.post("/api/v1/records/obligation", headers=h, json={"title": "Monthly uptime report", "contract_id": c["id"], "due_on": (TODAY + timedelta(days=3)).isoformat()})
    rows = client.get("/api/v1/reports/legal.renewals", headers=h).json()["rows"]
    assert rows[0][5] == (end - timedelta(days=30)).isoformat()
    assert client.post("/api/v1/jobs/obligations_check/run", headers=h).json()["summary"] == "1 notice deadline(s) ≤30d, 1 obligation(s) ≤7d"
    note = db.query(Notification).filter(Notification.title == "Legal dates coming up").one()
    assert "give notice by" in note.body and "(unverified)" in note.body


def test_contract_reader_requires_verbatim_quotes(client, make_workspace, scripted_llm, db):
    from app.departments.legal import Obligation

    w = make_workspace("acme")
    h = w["h"]
    doc = client.post("/api/v1/memory/documents", headers=h, json={"title": "MSA", "content": "7.2 The Supplier shall deliver a monthly uptime report within five (5) business days of month end."}).json()
    c = client.post("/api/v1/records/contract", headers=h, json={"title": "MSA", "document_id": doc["id"]}).json()
    scripted_llm["script"][:] = [
        llm_turn(uses=[("read_contract", {"contract_id": c["id"]})]),
        llm_turn(uses=[("add_obligation", {"contract_id": c["id"], "title": "Monthly uptime report", "recurrence": "monthly",
                                           "source_clause": "The Supplier shall deliver a monthly uptime report within five (5) business days of month end."}),
                       ("add_obligation", {"contract_id": c["id"], "title": "Invented penalty", "source_clause": "Supplier pays 10% penalty"})]),
        llm_turn(text="Done."),
    ]
    r = client.post("/api/v1/agents/contract_reader/run", headers=h, json={"input": str(c["id"])}).json()
    assert [t["status"] for t in r["tool_calls"]] == ["ok", "ok", "error"]
    assert "not an exact quote" in r["tool_calls"][2]["result"]["error"]
    o = db.query(Obligation).one()
    assert (o.title, o.verified) == ("Monthly uptime report", False)
    assert "<untrusted" in scripted_llm["results"][0][1]


def test_template_filler_requires_lawyer_review(client, make_workspace):
    w = make_workspace("acme")
    h = w["h"]
    t = client.post("/api/v1/records/legal_template", headers=h, json={"title": "Mutual NDA", "kind": "nda", "body": "This NDA is between {{company}} and {{counterparty}}, effective {{date}}."}).json()
    out = client.post("/api/v1/agents/template_filler/run", headers=h, json={"input": f"{t['id']}\ncompany: Mwangi Labs"}).json()["output"]
    assert out.startswith("Refused")
    assert client.patch(f"/api/v1/records/legal_template/{t['id']}", headers=h, json={"reviewed_on": "2026-09-01"}).status_code == 422
    client.patch(f"/api/v1/records/legal_template/{t['id']}", headers=h, json={"reviewed_on": "2026-09-01", "reviewed_by": "Adv. W. Njeri"})
    out = client.post("/api/v1/agents/template_filler/run", headers=h, json={"input": f"{t['id']}\ncompany: Mwangi Labs\ncounterparty: Vibanda Ltd"}).json()["output"]
    assert "between Mwangi Labs and Vibanda Ltd" in out and "MISSING values: date" in out
    edited = client.patch(f"/api/v1/records/legal_template/{t['id']}", headers=h, json={"body": "Changed {{company}}"}).json()
    assert edited["reviewed_on"] is None  # editing text voids the review


def test_fill_template_unit():
    text, missing = fill_template("{{a}} and {{ b }} and {{c}}", {"a": "1", "b": "2", "c": " "})
    assert text == "1 and 2 and  " and missing == ["c"]


def test_advisor_reads_legal_but_cannot_write(client, make_workspace, add_member):
    w = make_workspace("acme")
    adv = add_member(w["h"], "advisor", "a@acme.example.com")
    assert client.get("/api/v1/reports/legal.register", headers=adv).status_code == 200
    assert client.post("/api/v1/records/contract", headers=adv, json={"title": "x"}).status_code == 403
