"""
backend/owner/mpesa_match.py — does every M-Pesa payment on the statement have its sale, and every M-Pesa sale its payment?
(docs/v2/SPEC.md §4, sprint S6.2.)

The till says a guest paid KES 1,250 by M-Pesa at 12:41. The statement says KES 1,250 reached the till at 12:41:07. When the two agree the
money is where the sales say it is; when they do not, one of two things is true and the owner is told which:

  a sale with no payment    the till recorded an M-Pesa sale that the statement never shows (a guest who left, a sale rung up as M-Pesa that
                            was really cash, a payment that went to someone else's phone)
  a payment with no sale    money reached the till that no sale explains (an unrecorded sale, a deposit, a mistaken transfer)

Matching is deterministic, in four passes, each only over what the earlier ones left:

  1. receipt     the sale carries M-Pesa's own receipt number (the STK path) and the statement has it: the strongest evidence there is
  2. exact       the same amount, within `mpesa_match_minutes` of each other (the owner's setting); closest in time first, one to one
  3. grouped     one payment that is the sum of two to four sales close to it in time (a table paying the whole bill at once)
  4. split       one sale paid by two or three payments close to it in time (a bill split between phones)

Nothing here is a verdict: a gap is "a reason to look". The statement only covers the days it covers, so a sale outside those days is
neither matched nor flagged; it is counted as "outside the statement" and the owner is told.

The matching itself is a pure function (`match`) so it can be tested against hand-built and randomly generated days; `block` reads the
database (this restaurant only) and shapes the owner payload.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import combinations

from sqlalchemy import func

import models
from ai.analysis_clock import STALE_AFTER_DAYS
from owner.answers import kes_text
from owner.states import OwnerContext, block as state_block, iso, kes, no_data
from time_utils import EAT_OFFSET

MAX_GROUP = 4                     # several sales that were paid as one: at most this many
MAX_SPLIT = 3                     # one sale paid by several payments: at most this many
SHOWN = 20                        # how many unmatched items a block lists; the counts say how many there are


@dataclass(frozen=True)
class Sale:
    id: int
    at: datetime                  # naive UTC: when the bill was closed (else when it was opened)
    cents: int
    receipt: str | None = None


@dataclass(frozen=True)
class Payment:
    id: int
    at: datetime
    cents: int
    receipt: str = ""


@dataclass(frozen=True)
class Matched:
    kind: str                     # receipt | exact | grouped | split
    sales: tuple[int, ...]
    payments: tuple[int, ...]
    gap_seconds: int              # how far apart in time (the largest gap among the pieces)


@dataclass
class Result:
    matched: list[Matched]
    sales_without_payment: list[Sale]
    payments_without_sale: list[Payment]
    different_amounts: list[tuple[Sale, Payment]]        # the sale's own receipt is on the statement, for another amount


def _gap(a: datetime, b: datetime) -> float:
    return abs((a - b).total_seconds())


def match(sales: list[Sale], payments: list[Payment], minutes: int) -> Result:
    window = minutes * 60
    free_sales = {s.id: s for s in sales}
    free_pay = {p.id: p for p in payments}
    out: list[Matched] = []
    different: list[tuple[Sale, Payment]] = []

    # 1 ── receipt
    by_receipt = {p.receipt: p for p in payments if p.receipt}
    for s in sorted(sales, key=lambda s: (s.at, s.id)):
        p = by_receipt.get(s.receipt) if s.receipt else None
        if p is None or p.id not in free_pay or s.id not in free_sales:
            continue
        del free_sales[s.id], free_pay[p.id]
        if s.cents == p.cents:
            out.append(Matched("receipt", (s.id,), (p.id,), int(_gap(s.at, p.at))))
        else:
            different.append((s, p))

    # 2 ── exact amount, close in time, closest first
    pays_by_cents: dict[int, list[Payment]] = {}
    for p in free_pay.values():
        pays_by_cents.setdefault(p.cents, []).append(p)
    pairs = sorted(((_gap(s.at, p.at), s.at, s.id, p.id) for s in free_sales.values() for p in pays_by_cents.get(s.cents, ())
                    if _gap(s.at, p.at) <= window))
    for gap, _at, sid, pid in pairs:
        if sid in free_sales and pid in free_pay:
            del free_sales[sid], free_pay[pid]
            out.append(Matched("exact", (sid,), (pid,), int(gap)))

    # 3 ── grouped: one payment = the sum of two to four sales near it
    for p in sorted(list(free_pay.values()), key=lambda p: (p.at, p.id)):
        near = sorted((s for s in free_sales.values() if _gap(s.at, p.at) <= window and s.cents < p.cents), key=lambda s: (s.at, s.id))[:14]
        best = _best_subset(near, p.cents, MAX_GROUP, lambda s: _gap(s.at, p.at))
        if best:
            for s in best:
                del free_sales[s.id]
            del free_pay[p.id]
            out.append(Matched("grouped", tuple(sorted(s.id for s in best)), (p.id,), int(max(_gap(s.at, p.at) for s in best))))

    # 4 ── split: one sale = the sum of two or three payments near it
    for s in sorted(list(free_sales.values()), key=lambda s: (s.at, s.id)):
        near = sorted((p for p in free_pay.values() if _gap(s.at, p.at) <= window and p.cents < s.cents), key=lambda p: (p.at, p.id))[:14]
        best = _best_subset(near, s.cents, MAX_SPLIT, lambda p: _gap(s.at, p.at))
        if best:
            for p in best:
                del free_pay[p.id]
            del free_sales[s.id]
            out.append(Matched("split", (s.id,), tuple(sorted(p.id for p in best)), int(max(_gap(s.at, p.at) for p in best))))

    return Result(matched=sorted(out, key=lambda m: (m.sales, m.payments)),
                  sales_without_payment=sorted(free_sales.values(), key=lambda s: (s.at, s.id)),
                  payments_without_sale=sorted(free_pay.values(), key=lambda p: (p.at, p.id)),
                  different_amounts=different)


def _best_subset(items, target: int, max_size: int, gap):
    """The 2..max_size items whose cents add up to `target`, preferring the tightest in time (largest gap, then total gap, then ids)."""
    best, best_key = None, None
    for size in range(2, max_size + 1):
        for combo in combinations(items, size):
            if sum(i.cents for i in combo) != target:
                continue
            key = (max(gap(i) for i in combo), sum(gap(i) for i in combo), size, tuple(i.id for i in combo))
            if best_key is None or key < best_key:
                best, best_key = combo, key
    return best


# ── the owner block ──────────────────────────────────────────────────────────

def _sale_label(order: models.Order) -> str:
    where = f"Table {order.table_number}" if order.table_number else "Takeaway or delivery"
    n = sum(i.quantity or 0 for i in order.items)
    return f"{where}, {n} item{'s' if n != 1 else ''}"


def block(ctx: OwnerContext) -> dict:
    """The M-Pesa check for this restaurant: its statement lines against its M-Pesa sales, over the days the statement covers."""
    db, rid, minutes = ctx.db, ctx.rid, ctx.settings.mpesa_match_minutes
    lines = db.query(models.MpesaStatementLine).filter(
        models.MpesaStatementLine.restaurant_id == rid, models.MpesaStatementLine.paid_in_cents > 0).order_by(
        models.MpesaStatementLine.completed_at).all()
    if not lines:
        return no_data("Upload your M-Pesa statement to check it against your sales.")
    first, last = lines[0].completed_at, lines[-1].completed_at
    # The days the statement covers. It is exported for whole days, so it starts at midnight (Nairobi) of the day of its first payment; it ends
    # at its last payment (plus the window), not at midnight, because it may have been exported at three o'clock and says nothing of six.
    lo = (first + EAT_OFFSET).replace(hour=0, minute=0, second=0, microsecond=0) - EAT_OFFSET
    hi = last + timedelta(minutes=minutes)
    receipts = {line.receipt for line in lines}
    paid_at = func.coalesce(models.Order.completed_at, models.Order.created_at)
    orders = db.query(models.Order).filter(
        models.Order.restaurant_id == rid, models.Order.payment_method == models.PaymentMethod.MPESA, models.Order.is_paid.is_(True),
        models.Order.status != models.OrderStatus.CANCELLED, models.Order.total > 0).order_by(paid_at).all()
    inside = [o for o in orders if lo <= (o.completed_at or o.created_at) <= hi or (o.mpesa_receipt and o.mpesa_receipt in receipts)]
    inside_ids = {o.id for o in inside}
    outside = [o for o in orders if o.id not in inside_ids]
    sales = [Sale(o.id, o.completed_at or o.created_at, o.total or 0, o.mpesa_receipt or None) for o in inside]
    payments = [Payment(l.id, l.completed_at, l.paid_in_cents, l.receipt) for l in lines]
    result = match(sales, payments, minutes)
    by_order = {o.id: o for o in inside}
    by_line = {l.id: l for l in lines}

    sales_gap = result.sales_without_payment
    pay_gap = result.payments_without_sale
    matched_sales = [by_order[i] for m in result.matched for i in m.sales]
    kinds = {k: sum(1 for m in result.matched if m.kind == k) for k in ("receipt", "exact", "grouped", "split")}
    # Computed from a statement, not from the till: "not from the till" while it is recent, "stale" once the latest payment on it is old.
    base = state_block("stale" if (ctx.now - last).days > STALE_AFTER_DAYS else "not_from_pos", as_of=last, source="M-Pesa statement")
    sales_total = sum(s.cents for s in sales_gap)
    pay_total = sum(p.cents for p in pay_gap)
    head = _headline(len(sales), len(result.matched), sales_gap, pay_gap, result.different_amounts)
    return {
        **base,
        "headline": head,
        "window": {"from": iso(lo), "to": iso(last)},
        "checked": {"sales": len(sales), "payments": len(payments)},
        "matched": {"count": len(result.matched), "sales": len(matched_sales), "kes": kes(sum(s.total or 0 for s in matched_sales)), **kinds},
        "sales_without_payment": {
            "count": len(sales_gap), "kes": kes(sales_total),
            "items": [{"order_id": s.id, "at": iso(s.at), "kes": kes(s.cents), "what": _sale_label(by_order[s.id])} for s in sales_gap[-SHOWN:][::-1]]},
        "payments_without_sale": {
            "count": len(pay_gap), "kes": kes(pay_total),
            "items": [{"receipt": p.receipt, "at": iso(p.at), "kes": kes(p.cents), "from": by_line[p.id].details} for p in pay_gap[-SHOWN:][::-1]]},
        "different_amounts": [{"order_id": s.id, "receipt": p.receipt, "sale_kes": kes(s.cents), "payment_kes": kes(p.cents)} for s, p in result.different_amounts],
        "outside_statement": {"sales": len(outside), "kes": kes(sum(o.total or 0 for o in outside))},
        "assumption": {"setting": "mpesa_match_minutes", "value": minutes, "label": "Minutes between a sale and its payment"},
        "note": "A gap is a reason to look at the till and the statement, not a finding about anyone.",
    }


def _headline(n_sales: int, n_matched: int, sales_gap: list[Sale], pay_gap: list[Payment], different: list) -> str:
    if not n_sales and not pay_gap:
        return "The statement has payments, but no M-Pesa sales are recorded for those days."
    parts = []
    if sales_gap:
        parts.append(f"{len(sales_gap)} M-Pesa sale{'s' if len(sales_gap) != 1 else ''} ({kes_text(sum(s.cents for s in sales_gap) / 100)}) "
                     f"{'have' if len(sales_gap) != 1 else 'has'} no payment on your statement")
    if pay_gap:
        parts.append(f"{len(pay_gap)} payment{'s' if len(pay_gap) != 1 else ''} ({kes_text(sum(p.cents for p in pay_gap) / 100)}) "
                     f"{'have' if len(pay_gap) != 1 else 'has'} no sale recorded")
    if different:
        parts.append(f"{len(different)} sale{'s' if len(different) != 1 else ''} paid a different amount from the one recorded")
    if not parts:
        return f"All {n_sales} M-Pesa sale{'s' if n_sales != 1 else ''} match a payment on your statement."
    text = "; ".join(parts)
    return text[0].upper() + text[1:] + "."
