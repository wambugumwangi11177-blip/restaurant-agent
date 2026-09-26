"""
Department 5 — Finance (directive 105). Founder-only.

Records: invoice, payment, expense, subscription, cash_snapshot.
HARD RULE: the OS never moves money. There is no tool that pays, transfers or
         refunds; it records, reconciles, reminds and reports.
Tax:     NO tax rate or rule is built in. `tax_minor` is entered per invoice;
         `etims_reference` records the KRA eTIMS invoice number issued by your
         eTIMS system. Confirm VAT/eTIMS obligations with your accountant.
FX:      no exchange rates are invented; reports total per currency.
Agents:  bookkeeper (suggests expense categories from your own history — you
         confirm), collections (drafts overdue reminders as approval proposals),
         runway_reporter (deterministic).
Jobs:    none send money; `collections_check` notifies founders of newly overdue invoices.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import Date, ForeignKey, Integer, String, Text, UniqueConstraint, func, or_, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base
from app.departments._kit import Currency, In, Money, _ts, _ws, chain, default_currency, money, out_of, patch_of
from app.kernel import records
from app.kernel.agents.registry import AgentSpec, register_agent
from app.kernel.agents.tools import ToolContext, execute_tool
from app.kernel.departments import (
    Department,
    Job,
    Report,
    register_brief_section,
    register_department,
    register_job,
    register_report,
    table,
)
from app.kernel.models import Link, Organization, Person, Workspace
from app.kernel.notifications import founders, notify
from app.kernel.rbac import F, register_permissions
from app.kernel.tenancy import Principal, get_scoped, scoped

DEPT = "finance"


class Invoice(Base):
    __tablename__ = "fin_invoices"
    __table_args__ = (UniqueConstraint("workspace_id", "number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    number: Mapped[str] = mapped_column(String(40), nullable=False)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_minor: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_paid_minor: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    etims_reference: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    reminded_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Payment(Base):
    __tablename__ = "fin_payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("fin_invoices.id", ondelete="SET NULL"), index=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"))
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False, server_default="other")
    reference: Mapped[str | None] = mapped_column(String(100))
    received_on: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Expense(Base):
    __tablename__ = "fin_expenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    spent_on: Mapped[date] = mapped_column(Date, nullable=False)
    vendor: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str | None] = mapped_column(String(300))
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))
    suggested_category: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="unconfirmed")
    receipt_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Subscription(Base):
    __tablename__ = "fin_subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    vendor: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str | None] = mapped_column(String(300))
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    cadence: Mapped[str] = mapped_column(String(20), nullable=False, server_default="monthly")
    next_renewal_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class CashSnapshot(Base):
    __tablename__ = "fin_cash_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = _ws()
    account: Mapped[str] = mapped_column(String(100), nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    balance_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    note: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class InvoiceIn(In):
    title: str = Field(min_length=1, max_length=300, description="What the invoice is for")
    number: Optional[str] = Field(default=None, max_length=40, description="Leave empty to auto-number")
    organization_id: Optional[int] = None
    issue_date: date
    due_date: date
    currency: Currency = None
    subtotal_minor: Money
    tax_minor: Money = 0
    status: Literal["draft", "sent", "void"] = "draft"
    etims_reference: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = None


class PaymentIn(In):
    amount_minor: Money
    received_on: date
    invoice_id: Optional[int] = None
    organization_id: Optional[int] = None
    currency: Currency = None
    method: Literal["mpesa", "bank", "cash", "card", "other"] = "other"
    reference: Optional[str] = Field(default=None, max_length=100)
    title: Optional[str] = Field(default=None, max_length=300)


class ExpenseIn(In):
    spent_on: date
    vendor: str = Field(min_length=1, max_length=200)
    amount_minor: Money
    title: Optional[str] = Field(default=None, max_length=300)
    currency: Currency = None
    category: Optional[str] = Field(default=None, max_length=100)
    status: Literal["unconfirmed", "confirmed"] = "unconfirmed"
    receipt_document_id: Optional[int] = None


class SubscriptionIn(In):
    vendor: str = Field(min_length=1, max_length=200)
    amount_minor: Money
    title: Optional[str] = Field(default=None, max_length=300)
    currency: Currency = None
    cadence: Literal["monthly", "quarterly", "yearly"] = "monthly"
    next_renewal_on: Optional[date] = None
    status: Literal["active", "cancelled"] = "active"


class CashSnapshotIn(In):
    account: str = Field(min_length=1, max_length=100, description="e.g. 'Bank — current', 'M-Pesa till'")
    as_of: date
    balance_minor: int
    currency: Currency = None
    note: Optional[str] = Field(default=None, max_length=300)


# ── Hooks ────────────────────────────────────────────────────────────────────

def _invoice_hook(db: Session, p: Principal, values: dict, obj) -> dict:
    sub = values.get("subtotal_minor", obj.subtotal_minor if obj else 0)
    tax = values.get("tax_minor", obj.tax_minor if obj else 0)
    if "subtotal_minor" in values or "tax_minor" in values or obj is None:
        values["total_minor"] = sub + (tax or 0)
    issue = values.get("issue_date", obj.issue_date if obj else None)
    due = values.get("due_date", obj.due_date if obj else None)
    if issue and due and due < issue:
        raise HTTPException(422, "due_date is before issue_date")
    if obj is None and not values.get("number"):
        year = issue.year
        n = db.execute(select(func.count()).select_from(Invoice).where(
            Invoice.workspace_id == p.workspace_id, Invoice.number.like(f"INV-{year}-%"))).scalar_one()
        values["number"] = f"INV-{year}-{n + 1:04d}"
    elif obj is None or ("number" in values and values["number"] != obj.number):
        dup = db.execute(select(Invoice.id).where(Invoice.workspace_id == p.workspace_id,
                                                 Invoice.number == values["number"])).first()
        if dup:
            raise HTTPException(409, f"Invoice number {values['number']} already exists")
    if obj is not None and obj.amount_paid_minor and "currency" in values and values["currency"] != obj.currency:
        raise HTTPException(409, "Cannot change the currency of an invoice that has payments")
    return values


def recompute_invoice(db: Session, ws_id: int, invoice_id: int) -> None:
    inv = get_scoped(db, Invoice, invoice_id, ws_id)
    if inv is None:
        return
    paid = db.execute(select(func.coalesce(func.sum(Payment.amount_minor), 0)).where(
        Payment.workspace_id == ws_id, Payment.invoice_id == inv.id, Payment.currency == inv.currency)).scalar_one()
    inv.amount_paid_minor = int(paid)
    if inv.status == "void":
        return
    if paid >= inv.total_minor and inv.total_minor > 0:
        inv.status = "paid"
    elif paid > 0:
        inv.status = "partially_paid"
    elif inv.status in ("paid", "partially_paid"):
        inv.status = "sent"


def _payment_hook(db: Session, p: Principal, values: dict, obj) -> dict:
    if obj is not None and obj.invoice_id and "invoice_id" in values and values["invoice_id"] != obj.invoice_id:
        db.info.setdefault("fin_recompute", set()).add(obj.invoice_id)  # the invoice it moved away from
    inv_id = values.get("invoice_id", obj.invoice_id if obj else None)
    if inv_id:
        inv = get_scoped(db, Invoice, inv_id, p.workspace_id)
        cur = values.get("currency") or (obj.currency if obj else None) or inv.currency
        if cur != inv.currency:
            raise HTTPException(422, f"Payment currency {cur} differs from invoice currency {inv.currency}")
        values["currency"] = cur
        if not values.get("organization_id") and obj is None:
            values["organization_id"] = inv.organization_id
    return values


def _payment_after(db: Session, p: Principal, pay: Payment, deleted: bool) -> None:
    db.flush()
    targets = db.info.pop("fin_recompute", set())
    if pay.invoice_id:
        targets.add(pay.invoice_id)
    for inv_id in targets:
        recompute_invoice(db, p.workspace_id, inv_id)


def _expense_hook(db: Session, p: Principal, values: dict, obj) -> dict:
    status_ = values.get("status", obj.status if obj else "unconfirmed")
    category = values.get("category", obj.category if obj else None)
    if status_ == "confirmed" and not category:
        raise HTTPException(422, "An expense needs a category before it can be confirmed")
    return values


# ── Logic & reports ──────────────────────────────────────────────────────────

def _today(db: Session, ws_id: int) -> date:
    ws = db.get(Workspace, ws_id)
    return datetime.now(ZoneInfo(ws.timezone if ws else "Africa/Nairobi")).date()


def overdue_invoices(db: Session, ws_id: int) -> list[Invoice]:
    return list(db.execute(scoped(Invoice, ws_id).where(
        Invoice.status.in_(["sent", "partially_paid"]), Invoice.due_date < _today(db, ws_id))
        .order_by(Invoice.due_date)).scalars())


def receivables_report(db: Session, p: Principal, params: dict) -> dict:
    today = _today(db, p.workspace_id)
    rows = []
    for inv in db.execute(scoped(Invoice, p.workspace_id).where(Invoice.status.in_(["sent", "partially_paid"]))
                          .order_by(Invoice.due_date)).scalars():
        org = db.get(Organization, inv.organization_id) if inv.organization_id else None
        days = (today - inv.due_date).days
        rows.append([inv.number, org.name if org else "—", money(inv.total_minor - inv.amount_paid_minor, inv.currency),
                     inv.due_date.isoformat(), f"{days} days overdue" if days > 0 else "not due"])
    return table("Receivables", f"{len(rows)} unpaid invoice(s)", ["Invoice", "Client", "Outstanding", "Due", "Age"], rows)


def _month_bounds(month: str | None, today: date) -> tuple[date, date]:
    if month:
        try:
            y, m = (int(x) for x in month.split("-"))
            start = date(y, m, 1)
        except ValueError:
            raise HTTPException(422, "month must be YYYY-MM") from None
    else:
        start = today.replace(day=1)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start, end


def monthly_report(db: Session, p: Principal, params: dict) -> dict:
    start, end = _month_bounds(params.get("month"), _today(db, p.workspace_id))
    ws = p.workspace_id
    received = db.execute(select(Payment.currency, func.sum(Payment.amount_minor)).where(
        Payment.workspace_id == ws, Payment.received_on >= start, Payment.received_on < end).group_by(Payment.currency)).all()
    spent = db.execute(select(Expense.category, Expense.currency, func.sum(Expense.amount_minor)).where(
        Expense.workspace_id == ws, Expense.status == "confirmed", Expense.spent_on >= start, Expense.spent_on < end)
        .group_by(Expense.category, Expense.currency).order_by(Expense.category)).all()
    unconfirmed = db.execute(select(func.count()).select_from(Expense).where(
        Expense.workspace_id == ws, Expense.status == "unconfirmed", Expense.spent_on >= start, Expense.spent_on < end)).scalar_one()
    rows = [["Received", "—", money(v, c)] for c, v in received]
    rows += [["Spent", cat or "(none)", money(v, c)] for cat, c, v in spent]
    summary = f"{start:%B %Y}. Only confirmed expenses count; {unconfirmed} unconfirmed expense(s) are excluded."
    return table("Month", summary, ["Flow", "Category", "Amount"], rows)


def runway(db: Session, ws_id: int) -> dict:
    ws = db.get(Workspace, ws_id)
    cur = ws.currency
    latest: dict[str, CashSnapshot] = {}
    for s in db.execute(scoped(CashSnapshot, ws_id).order_by(CashSnapshot.as_of)).scalars():
        latest[s.account] = s
    cash = sum(s.balance_minor for s in latest.values() if s.currency == cur)
    other_ccy = sorted({s.currency for s in latest.values() if s.currency != cur})
    today = _today(db, ws_id)
    this_month = today.replace(day=1)
    months = []
    start = this_month
    for _ in range(3):  # last 3 complete months
        end = start
        start = (start - timedelta(days=1)).replace(day=1)
        inflow = db.execute(select(func.coalesce(func.sum(Payment.amount_minor), 0)).where(
            Payment.workspace_id == ws_id, Payment.currency == cur, Payment.received_on >= start, Payment.received_on < end)).scalar_one()
        outflow = db.execute(select(func.coalesce(func.sum(Expense.amount_minor), 0)).where(
            Expense.workspace_id == ws_id, Expense.currency == cur, Expense.status == "confirmed",
            Expense.spent_on >= start, Expense.spent_on < end)).scalar_one()
        months.append((start, int(inflow), int(outflow)))
    net_burn = sum(o - i for _, i, o in months) / 3
    return {"currency": cur, "cash_minor": cash, "accounts": {k: (v.balance_minor, v.currency, v.as_of) for k, v in latest.items()},
            "other_currencies": other_ccy, "months": months, "avg_net_burn_minor": net_burn,
            "runway_months": (cash / net_burn) if net_burn > 0 else None}


def runway_report(db: Session, p: Principal, params: dict) -> dict:
    r = runway(db, p.workspace_id)
    c = r["currency"]
    rows = [[f"{m:%b %Y}", money(i, c), money(o, c), money(o - i, c)] for m, i, o in r["months"]]
    if not r["accounts"]:
        summary = "No cash snapshots recorded yet — add one per bank/M-Pesa account to compute runway."
    elif r["runway_months"] is None:
        summary = f"Cash {money(r['cash_minor'], c)}. Not burning cash over the last 3 months (inflow ≥ confirmed outflow)."
    else:
        summary = (f"Cash {money(r['cash_minor'], c)}; average net burn {money(int(r['avg_net_burn_minor']), c)}/month "
                   f"→ about {r['runway_months']:.1f} months of runway.")
    if r["other_currencies"]:
        summary += f" Balances in {', '.join(r['other_currencies'])} are NOT included (no exchange rates are assumed)."
    return table("Runway", summary + " Based on recorded payments and confirmed expenses only.",
                 ["Month", "Received", "Confirmed spend", "Net burn"], rows)


def unmatched_payments_report(db: Session, p: Principal, params: dict) -> dict:
    """Payments with no invoice, each with the open invoices whose outstanding amount equals it."""
    rows = []
    open_inv = db.execute(scoped(Invoice, p.workspace_id).where(Invoice.status.in_(["sent", "partially_paid"]))).scalars().all()
    for pay in db.execute(scoped(Payment, p.workspace_id).where(Payment.invoice_id.is_(None)).order_by(Payment.received_on)).scalars():
        cands = [i.number for i in open_inv if i.currency == pay.currency and i.total_minor - i.amount_paid_minor == pay.amount_minor]
        rows.append([pay.id, pay.received_on.isoformat(), money(pay.amount_minor, pay.currency), pay.reference or "—",
                     ", ".join(cands) or "no exact match"])
    return table("Unmatched payments", "Exact-amount candidates only; you decide the match.",
                 ["#", "Received", "Amount", "Reference", "Candidate invoices"], rows)


def brief(db: Session, ws_id: int) -> list[str]:
    out = [f"overdue: {i.number} {money(i.total_minor - i.amount_paid_minor, i.currency)} (due {i.due_date})"
           for i in overdue_invoices(db, ws_id)[:5]]
    soon = _today(db, ws_id) + timedelta(days=7)
    out += [f"renews {s.next_renewal_on}: {s.vendor} {money(s.amount_minor, s.currency)}" for s in db.execute(
        scoped(Subscription, ws_id).where(Subscription.status == "active", Subscription.next_renewal_on <= soon)).scalars()]
    n = db.execute(select(func.count()).select_from(Expense).where(Expense.workspace_id == ws_id, Expense.status == "unconfirmed")).scalar_one()
    if n:
        out.append(f"{n} expense(s) waiting for your confirmation")
    return out


def collections_check(db: Session, ws_id: int) -> str:
    items = overdue_invoices(db, ws_id)
    fresh = [i for i in items if i.reminded_on is None]
    if fresh:
        body = "\n".join(f"{i.number}: {money(i.total_minor - i.amount_paid_minor, i.currency)} due {i.due_date}" for i in fresh)
        for uid in founders(db, ws_id):
            notify(db, ws_id, uid, f"{len(fresh)} invoice(s) became overdue", body, link="/d/finance")
    return f"{len(items)} overdue, {len(fresh)} not yet reminded"


# ── Agents ───────────────────────────────────────────────────────────────────

def _bookkeeper(ctx: ToolContext, text: str) -> tuple[str, list[dict]]:
    ws = ctx.principal.workspace_id
    history: dict[str, Counter] = {}
    for vendor, cat in ctx.db.execute(select(Expense.vendor, Expense.category).where(
            Expense.workspace_id == ws, Expense.status == "confirmed", Expense.category.is_not(None))):
        history.setdefault(vendor.strip().lower(), Counter())[cat] += 1
    lines, suggested = [], 0
    for e in ctx.db.execute(scoped(Expense, ws).where(Expense.status == "unconfirmed")).scalars():
        counts = history.get(e.vendor.strip().lower())
        if counts:
            cat, n = counts.most_common(1)[0]
            if e.suggested_category != cat:
                e.suggested_category = cat
            suggested += 1
            lines.append(f"• {e.vendor} {money(e.amount_minor, e.currency)} on {e.spent_on}: suggest '{cat}' ({n} past)")
        else:
            lines.append(f"• {e.vendor} {money(e.amount_minor, e.currency)} on {e.spent_on}: no history — categorise manually")
    head = f"{suggested} suggestion(s). Nothing is confirmed until you set category + status=confirmed."
    return "\n".join([head, *lines]) if lines else "No unconfirmed expenses.", []


def _contact_email(db: Session, ws_id: int, org_id: int | None) -> str | None:
    if not org_id:
        return None
    person_ids = [lk.from_id if lk.from_type == "person" else lk.to_id for lk in db.execute(select(Link).where(
        Link.workspace_id == ws_id, or_((Link.from_type == "person") & (Link.to_type == "organization") & (Link.to_id == org_id),
                                        (Link.to_type == "person") & (Link.from_type == "organization") & (Link.from_id == org_id)))).scalars()]
    for pid in person_ids:
        person = get_scoped(db, Person, pid, ws_id)
        if person and person.email:
            return person.email
    return None


def _collections(ctx: ToolContext, text: str) -> tuple[str, list[dict]]:
    ws = ctx.principal.workspace_id
    lines = []
    for inv in overdue_invoices(ctx.db, ws):
        org = ctx.db.get(Organization, inv.organization_id) if inv.organization_id else None
        to = _contact_email(ctx.db, ws, inv.organization_id)
        outstanding = money(inv.total_minor - inv.amount_paid_minor, inv.currency)
        if not to:
            lines.append(f"• {inv.number}: no contact email linked to {org.name if org else 'the client'} — link a person to the organization")
            continue
        body = (f"Hello,\n\nThis is a friendly reminder that invoice {inv.number} ({inv.title}) for {outstanding} "
                f"was due on {inv.due_date:%d %B %Y}. If you have already paid, please reply with the payment reference "
                f"so we can match it.\n\nThank you.")
        out = execute_tool(ctx, "send_email", {"to": to, "subject": f"Payment reminder: invoice {inv.number}", "body": body})
        if out["status"] in ("pending_approval", "executed"):
            inv.reminded_on = datetime.now(ZoneInfo("UTC")).date()
        lines.append(f"• {inv.number} {outstanding} → reminder to {to}: {out['status']} (proposal #{out.get('proposal_id')})")
    return ("\n".join(lines) if lines else "No overdue invoices."), []


def _runway_agent(ctx: ToolContext, text: str) -> tuple[str, list[dict]]:
    return runway_report(ctx.db, ctx.principal, {})["summary"], []


def register() -> None:
    register_permissions({"finance.read": {F}, "finance.write": {F}})
    perms = dict(read_perm="finance.read", write_perm="finance.write", delete_perm="finance.write", department=DEPT)
    rr = records.register_record_type
    rr("invoice", records.RecordType(Invoice, InvoiceIn, patch_of(InvoiceIn), out_of(Invoice), ("number", "title", "notes"),
                                     label="Invoices", refs={"organization_id": "organization"},
                                     prepare=chain(default_currency, _invoice_hook), **perms))
    rr("payment", records.RecordType(Payment, PaymentIn, patch_of(PaymentIn), out_of(Payment), ("reference", "title"),
                                     label="Payments", title_field="reference",
                                     refs={"invoice_id": "invoice", "organization_id": "organization"},
                                     prepare=chain(_payment_hook, default_currency), after=_payment_after, **perms))
    rr("expense", records.RecordType(Expense, ExpenseIn, patch_of(ExpenseIn), out_of(Expense), ("vendor", "title", "category"),
                                     label="Expenses", title_field="vendor", refs={"receipt_document_id": "document"},
                                     prepare=chain(default_currency, _expense_hook), **perms))
    rr("subscription", records.RecordType(Subscription, SubscriptionIn, patch_of(SubscriptionIn), out_of(Subscription),
                                          ("vendor", "title"), label="Subscriptions", title_field="vendor",
                                          prepare=default_currency, **perms))
    rr("cash_snapshot", records.RecordType(CashSnapshot, CashSnapshotIn, patch_of(CashSnapshotIn), out_of(CashSnapshot),
                                           ("account", "note"), label="Cash snapshots", title_field="account",
                                           prepare=default_currency, **perms))
    for key, label, fn, params in (
        ("finance.receivables", "Receivables", receivables_report, ()),
        ("finance.month", "Month in/out", monthly_report, ("month",)),
        ("finance.runway", "Runway", runway_report, ()),
        ("finance.unmatched", "Unmatched payments", unmatched_payments_report, ()),
    ):
        register_report(Report(key, DEPT, label, fn, "finance.read", params=params))
    register_job(Job("collections_check", DEPT, collections_check, "daily 08:00 Africa/Nairobi"))
    register_brief_section(DEPT, "Finance", brief)
    register_agent(AgentSpec(name="bookkeeper", description="Suggests expense categories from your own confirmed history.",
                             handler=_bookkeeper, permission="finance.write", input_hint="(no input needed)"))
    register_agent(AgentSpec(name="collections", description="Drafts overdue-invoice reminders as approval proposals.",
                             handler=_collections, permission="finance.write", input_hint="(no input needed)"))
    register_agent(AgentSpec(name="runway_reporter", description="Cash, burn and runway from recorded data.",
                             handler=_runway_agent, permission="finance.read", input_hint="(no input needed)"))
    register_department(Department(DEPT, "Finance", 5, "Invoices, payments, expenses and runway. Never moves money.",
                                   "finance.read", ("invoice", "payment", "expense", "subscription", "cash_snapshot"),
                                   ("bookkeeper", "collections", "runway_reporter"), "directives/105_finance.md"))
