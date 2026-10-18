"""
S6.2 — the M-Pesa check: does every payment on the statement have its sale, and every M-Pesa sale its payment? (docs/v2/SPEC.md §4 P6.)

What this pins:
  * the matching, as a pure function: by receipt, by amount within the owner's minutes (closest first, one to one), several sales paid as
    one payment, one sale paid by several payments — and both directions of gap; deterministic whatever order things arrive in; every sale
    and payment ends up in exactly one place; on randomly generated days it finds exactly the gaps that were planted;
  * the block the owner sees: its state (a statement is not the till: `not_from_pos`, `stale` once old), the days it covers, what it
    counts, what it lists, the sentence made from those numbers, KES at the edge; sales outside the statement's days are counted, never
    flagged; cash, unpaid, cancelled, free and other restaurants' sales are never in it;
  * the minutes are the owner's setting (`mpesa_match_minutes`, migration 056): changing it changes the answer;
  * it reaches Zone 1 (the totals), the cash panel, one more "thing to look at", Ask LEVIII and the weekly and monthly reports;
  * everything is this restaurant's own.
"""
import os
import random
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa

import auth
import models
from owner import areas, mpesa_match
from owner.answers import ungrounded
from owner.mpesa_match import Payment, Sale, match
from owner.mpesa_statement import import_statement
from owner.settings import update_settings
from owner.states import OwnerContext
from tests.fixtures import golden_restaurant as gr
from time_utils import EAT_OFFSET, utcnow

BACKEND = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 10, 14, 9, 0, 0)                      # a Wednesday, 12:00 in Nairobi


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


# ═════════════════════════════════════════════════════════════════════════════
# The matching, as a pure function
# ═════════════════════════════════════════════════════════════════════════════

def kinds(result):
    return sorted((m.kind, m.sales, m.payments) for m in result.matched)


def test_a_payment_at_the_same_amount_close_in_time_is_the_sales_payment():
    r = match([Sale(1, at(0), 125_000)], [Payment(10, at(3), 125_000)], 10)
    assert kinds(r) == [("exact", (1,), (10,))] and r.sales_without_payment == [] and r.payments_without_sale == []
    assert r.matched[0].gap_seconds == 180


@pytest.mark.parametrize("minutes_apart,matched", [(0, True), (9, True), (10, True), (10.01, False), (11, False), (-10, True), (-10.01, False)])
def test_the_window_is_the_owners_minutes_inclusive(minutes_apart, matched):
    r = match([Sale(1, at(0), 50_000)], [Payment(2, at(minutes_apart), 50_000)], 10)
    assert bool(r.matched) is matched and bool(r.sales_without_payment) is (not matched) and bool(r.payments_without_sale) is (not matched)


def test_a_different_amount_is_never_the_same_payment():
    r = match([Sale(1, at(0), 50_000)], [Payment(2, at(1), 50_001)], 10)
    assert r.matched == [] and [s.id for s in r.sales_without_payment] == [1] and [p.id for p in r.payments_without_sale] == [2]


def test_one_payment_pays_one_sale():
    r = match([Sale(1, at(0), 30_000), Sale(2, at(1), 30_000)], [Payment(9, at(1), 30_000)], 10)
    assert len(r.matched) == 1 and len(r.sales_without_payment) == 1 and r.payments_without_sale == []


def test_among_equal_amounts_the_closest_in_time_pairs_first():
    sales = [Sale(1, at(0), 30_000), Sale(2, at(8), 30_000)]
    r = match(sales, [Payment(7, at(9), 30_000), Payment(8, at(1), 30_000)], 10)
    assert kinds(r) == [("exact", (1,), (8,)), ("exact", (2,), (7,))]


def test_a_sale_nobody_paid_and_a_payment_nobody_owes_are_both_gaps():
    r = match([Sale(1, at(0), 10_000), Sale(2, at(5), 20_000)], [Payment(7, at(5), 20_000), Payment(8, at(6), 99_900)], 10)
    assert kinds(r) == [("exact", (2,), (7,))]
    assert [s.id for s in r.sales_without_payment] == [1] and [p.id for p in r.payments_without_sale] == [8]


def test_nothing_in_nothing_out():
    r = match([], [], 10)
    assert (r.matched, r.sales_without_payment, r.payments_without_sale, r.different_amounts) == ([], [], [], [])
    assert [s.id for s in match([Sale(1, at(0), 5)], [], 10).sales_without_payment] == [1]
    assert [p.id for p in match([], [Payment(1, at(0), 5)], 10).payments_without_sale] == [1]


# ── by receipt ───────────────────────────────────────────────────────────────

def test_a_receipt_on_the_sale_matches_whatever_the_time():
    r = match([Sale(1, at(0), 80_000, "SJE4K2L9QA")], [Payment(5, at(300), 80_000, "SJE4K2L9QA")], 10)
    assert kinds(r) == [("receipt", (1,), (5,))]


def test_a_receipt_beats_an_amount_that_would_have_matched_another_sale():
    sales = [Sale(1, at(0), 80_000, "SJE4K2L9QA"), Sale(2, at(1), 80_000)]
    r = match(sales, [Payment(5, at(2), 80_000, "SJE4K2L9QA"), Payment(6, at(2), 80_000, "SJE4K2LAB7")], 10)
    assert kinds(r) == [("exact", (2,), (6,)), ("receipt", (1,), (5,))]


def test_the_same_receipt_for_another_amount_is_a_different_amount_not_a_match():
    s, p = Sale(1, at(0), 80_000, "SJE4K2L9QA"), Payment(5, at(1), 75_000, "SJE4K2L9QA")
    r = match([s], [p], 10)
    assert r.matched == [] and r.different_amounts == [(s, p)]
    assert r.sales_without_payment == [] and r.payments_without_sale == []             # it is its own finding, not two unrelated gaps


def test_a_receipt_the_statement_does_not_have_falls_back_to_amount_and_time():
    r = match([Sale(1, at(0), 80_000, "SJE4K2L9QA")], [Payment(5, at(2), 80_000, "SJE4K2LZZZ")], 10)
    assert kinds(r) == [("exact", (1,), (5,))]


# ── grouped: several sales, one payment ──────────────────────────────────────

@pytest.mark.parametrize("amounts", [(30_000, 45_000), (10_000, 20_000, 30_500), (10_000, 20_000, 30_000, 40_500)])
def test_several_sales_paid_as_one_payment(amounts):
    sales = [Sale(i + 1, at(i), c) for i, c in enumerate(amounts)]
    r = match(sales, [Payment(99, at(len(amounts) / 2), sum(amounts))], 10)
    assert kinds(r) == [("grouped", tuple(range(1, len(amounts) + 1)), (99,))]
    assert r.sales_without_payment == [] and r.payments_without_sale == []


def test_five_sales_are_too_many_to_call_one_payment():
    sales = [Sale(i + 1, at(i), 10_000) for i in range(5)]
    r = match(sales, [Payment(99, at(2), 50_000)], 10)
    assert r.matched == [] and len(r.sales_without_payment) == 5 and len(r.payments_without_sale) == 1


def test_a_group_must_be_close_to_its_payment_in_time():
    sales = [Sale(1, at(0), 30_000), Sale(2, at(40), 45_000)]
    assert match(sales, [Payment(9, at(20), 75_000)], 10).matched == []


def test_the_group_closest_in_time_wins():
    sales = [Sale(1, at(0), 20_000), Sale(2, at(1), 30_000), Sale(3, at(9), 30_000)]
    r = match(sales, [Payment(9, at(1), 50_000)], 10)
    assert kinds(r) == [("grouped", (1, 2), (9,))] and [s.id for s in r.sales_without_payment] == [3]


def test_an_exact_match_is_never_pulled_into_a_group():
    sales = [Sale(1, at(0), 20_000), Sale(2, at(1), 30_000)]
    r = match(sales, [Payment(8, at(0), 20_000), Payment(9, at(1), 50_000)], 10)
    assert kinds(r) == [("exact", (1,), (8,))] and [s.id for s in r.sales_without_payment] == [2] and [p.id for p in r.payments_without_sale] == [9]


# ── split: one sale, several payments ────────────────────────────────────────

@pytest.mark.parametrize("parts", [(40_000, 60_000), (20_000, 30_000, 50_500)])
def test_one_sale_paid_by_several_phones(parts):
    payments = [Payment(10 + i, at(i), c) for i, c in enumerate(parts)]
    r = match([Sale(1, at(1), sum(parts))], payments, 10)
    assert kinds(r) == [("split", (1,), tuple(10 + i for i in range(len(parts))))] and r.payments_without_sale == []


def test_four_payments_are_too_many_to_call_one_sale():
    r = match([Sale(1, at(1), 40_000)], [Payment(10 + i, at(i), 10_000) for i in range(4)], 10)
    assert r.matched == [] and len(r.payments_without_sale) == 4


# ── properties ───────────────────────────────────────────────────────────────

def _day(rng: random.Random, n_sales: int, n_missing: int, n_stray: int):
    """A day of M-Pesa sales at least 25 minutes apart with distinct amounts, each paid within 1-6 minutes; `n_missing` payments dropped, `n_stray` added."""
    sales, payments, t = [], [], 0.0
    for i in range(n_sales):
        t += rng.uniform(25, 60)
        cents = 10_000 + i * 997 + rng.randrange(0, 900)
        sales.append(Sale(i + 1, at(t), cents))
        payments.append(Payment(1000 + i, at(t + rng.uniform(1, 6)), cents))
    dropped = set(rng.sample(range(n_sales), min(n_missing, n_sales)))
    payments = [p for i, p in enumerate(payments) if i not in dropped]
    for j in range(n_stray):
        payments.append(Payment(5000 + j, at(rng.uniform(0, t)), 777_000 + j))
    return sales, payments, {s.id for i, s in enumerate(sales) if i in dropped}, {5000 + j for j in range(n_stray)}


@pytest.mark.parametrize("seed", range(60))
def test_on_a_random_day_it_finds_exactly_the_gaps_that_were_planted(seed):
    rng = random.Random(seed)
    sales, payments, missing, stray = _day(rng, rng.randrange(1, 40), rng.randrange(0, 4), rng.randrange(0, 4))
    r = match(sales, payments, 10)
    assert {s.id for s in r.sales_without_payment} == missing
    assert {p.id for p in r.payments_without_sale} == stray
    assert len(r.matched) == len(sales) - len(missing)


@pytest.mark.parametrize("seed", range(40))
def test_every_sale_and_every_payment_ends_up_in_exactly_one_place(seed):
    rng = random.Random(1000 + seed)
    sales = [Sale(i, at(rng.uniform(0, 90)), rng.choice((10_000, 20_000, 30_000, 50_000, 60_000)), None) for i in range(rng.randrange(0, 25))]
    payments = [Payment(100 + i, at(rng.uniform(0, 90)), rng.choice((10_000, 20_000, 30_000, 50_000, 60_000, 80_000)), "") for i in range(rng.randrange(0, 25))]
    r = match(sales, payments, rng.choice((2, 10, 30)))
    used_s = [i for m in r.matched for i in m.sales] + [s.id for s in r.sales_without_payment] + [s.id for s, _p in r.different_amounts]
    used_p = [i for m in r.matched for i in m.payments] + [p.id for p in r.payments_without_sale] + [p.id for _s, p in r.different_amounts]
    assert sorted(used_s) == sorted(s.id for s in sales) and sorted(used_p) == sorted(p.id for p in payments)
    for m in r.matched:                                                   # whatever was matched adds up, to the cent
        by_s, by_p = {s.id: s for s in sales}, {p.id: p for p in payments}
        assert sum(by_s[i].cents for i in m.sales) == sum(by_p[i].cents for i in m.payments)
        assert m.gap_seconds <= 30 * 60


@pytest.mark.parametrize("seed", range(20))
def test_the_answer_does_not_depend_on_the_order_things_arrive_in(seed):
    rng = random.Random(2000 + seed)
    sales = [Sale(i, at(rng.uniform(0, 60)), rng.choice((10_000, 20_000, 30_000, 50_000)), None) for i in range(15)]
    payments = [Payment(100 + i, at(rng.uniform(0, 60)), rng.choice((10_000, 20_000, 30_000, 50_000, 60_000)), "") for i in range(15)]
    first = match(sales, payments, 10)
    rng.shuffle(sales)
    rng.shuffle(payments)
    again = match(sales, payments, 10)
    assert kinds(first) == kinds(again) and first.sales_without_payment == again.sales_without_payment and first.payments_without_sale == again.payments_without_sale


def test_a_wider_window_never_matches_fewer():
    rng = random.Random(7)
    sales = [Sale(i, at(rng.uniform(0, 120)), rng.choice((10_000, 20_000, 30_000)), None) for i in range(20)]
    payments = [Payment(100 + i, at(rng.uniform(0, 120)), rng.choice((10_000, 20_000, 30_000)), "") for i in range(20)]
    counts = [len(match(sales, payments, m).matched) for m in (2, 5, 10, 20, 60)]
    assert counts == sorted(counts) and counts[-1] > counts[0]


# ═════════════════════════════════════════════════════════════════════════════
# The block the owner sees
# ═════════════════════════════════════════════════════════════════════════════

def csv_statement(payments: list[tuple[str, datetime, int]], name: str = "Customer Payment from 2547****1234 - JOHN KAMAU") -> bytes:
    rows = ["Receipt No.,Completion Time,Details,Transaction Status,Paid In,Withdrawn,Balance"]
    for receipt, when, cents in payments:
        rows.append(f'{receipt},{(when + EAT_OFFSET):%Y-%m-%d %H:%M:%S},{name},Completed,"{cents / 100:,.2f}",,')
    return ("\n".join(rows) + "\n").encode()


class Day:
    """A golden restaurant with M-Pesa sales and a statement, around `base` (default: an hour ago)."""

    def __init__(self, db, suffix="m", base=None):
        self.db = db
        self.g = gr.build_skeleton(db, suffix=suffix)
        # nine o'clock yesterday, Nairobi time: a fixed hour of a day that is over, so no test straddles midnight or runs "in the future"
        midnight = (utcnow() + EAT_OFFSET).replace(hour=0, minute=0, second=0, microsecond=0) - EAT_OFFSET
        self.base = base or (midnight - timedelta(days=1) + timedelta(hours=9))
        self.n = 0
        self.lines: list[tuple[str, datetime, int]] = []

    def sale(self, minute: float, cents: int, *, paid=True, method=models.PaymentMethod.MPESA, status=models.OrderStatus.SERVED, receipt=None, table=None):
        dish = self.g.items["Pilau"]
        order = gr.add_order(self.db, self.g, [(dish, 1, cents)], self.base + timedelta(minutes=minute), payment=method, paid=paid, status=status)
        order.mpesa_receipt, order.table_number = receipt, table
        self.db.commit()
        return order

    def pay(self, minute: float, cents: int, receipt=None):
        self.n += 1
        self.lines.append((receipt or f"SJE{self.n:07d}", self.base + timedelta(minutes=minute), cents))

    def upload(self, who=None):
        result = import_statement(self.db, self.g.rid, (who or self.g.owner).id, "s.csv", csv_statement(self.lines))
        assert result["new"] == len(self.lines)
        return result

    def ctx(self):
        self.db.expire_all()
        return OwnerContext(self.db, self.g.owner, self.g.restaurant)

    def block(self):
        return mpesa_match.block(self.ctx())


def full_day(db, suffix="m", n=6):
    d = Day(db, suffix)
    for i in range(n):
        d.sale(i * 30, 100_000 + i * 5_000, table=i + 1)
        d.pay(i * 30 + 3, 100_000 + i * 5_000)
    d.upload()
    return d


def test_without_a_statement_it_says_to_upload_one(db_session):
    d = Day(db_session)
    d.sale(0, 100_000)
    b = d.block()
    assert b["state"] == "no_data" and "Upload your M-Pesa statement" in b["reason"]


def test_when_everything_matches_it_says_so_and_names_its_source(db_session):
    d = full_day(db_session)
    b = d.block()
    assert b["state"] == "not_from_pos" and b["source"] == "M-Pesa statement"
    assert b["headline"] == "All 6 M-Pesa sales match a payment on your statement."
    assert (b["checked"], b["matched"]["count"], b["matched"]["exact"]) == ({"sales": 6, "payments": 6}, 6, 6)
    assert b["matched"]["kes"] == sum(100_000 + i * 5_000 for i in range(6)) / 100
    assert b["sales_without_payment"] == {"count": 0, "kes": 0.0, "items": []} and b["payments_without_sale"]["count"] == 0
    assert b["assumption"] == {"setting": "mpesa_match_minutes", "value": 10, "label": "Minutes between a sale and its payment"}
    assert b["window"]["from"].endswith("+00:00") and ungrounded({"headline": b["headline"], **b}) == []


def test_three_sales_the_statement_never_shows_are_named_and_added_up(db_session):
    d = Day(db_session)
    for i in range(9):
        d.sale(i * 30, 100_000 + i * 5_000, table=i + 1)
        if i not in (2, 5, 7):
            d.pay(i * 30 + 2, 100_000 + i * 5_000)
    d.upload()
    b = d.block()
    gap = b["sales_without_payment"]
    assert gap["count"] == 3 and gap["kes"] == (110_000 + 125_000 + 135_000) / 100
    assert [x["kes"] for x in gap["items"]] == [1350.0, 1250.0, 1100.0]                  # newest first
    assert gap["items"][0]["what"] == "Table 8, 1 item" and all(x["at"].endswith("+00:00") for x in gap["items"])
    assert b["headline"] == "3 M-Pesa sales (KES 3,700) have no payment on your statement."
    assert ungrounded({"headline": b["headline"], **b}) == []


def test_a_payment_no_sale_explains_is_the_other_gap(db_session):
    d = full_day(db_session)
    d.pay(100, 250_000)
    d.upload_more = None
    import_statement(db_session, d.g.rid, d.g.owner.id, "more.csv", csv_statement([d.lines[-1]], name="Customer Payment from 2547****9999 - SOMEONE ELSE"))
    b = d.block()
    p = b["payments_without_sale"]
    assert p["count"] == 1 and p["kes"] == 2500.0 and p["items"][0]["from"].endswith("SOMEONE ELSE") and p["items"][0]["receipt"] == d.lines[-1][0]
    assert b["headline"] == "1 payment (KES 2,500) has no sale recorded."


def test_both_gaps_at_once_are_both_in_the_sentence(db_session):
    d = Day(db_session)
    d.sale(0, 100_000)
    d.sale(60, 200_000)
    d.pay(1, 100_000)
    d.pay(30, 777_700)
    d.pay(61, 200_000)
    d.upload()
    b = d.block()
    assert b["headline"] == "1 payment (KES 7,777) has no sale recorded." and b["sales_without_payment"]["count"] == 0
    d.sale(40, 300_000)                                                    # between the payment at 30 and the one at 61: inside the days covered
    b = d.block()
    assert b["headline"] == "1 M-Pesa sale (KES 3,000) has no payment on your statement; 1 payment (KES 7,777) has no sale recorded."


def test_grouped_and_split_payments_are_found_and_counted_by_kind(db_session):
    d = Day(db_session)
    d.sale(0, 30_000)
    d.sale(4, 45_000)
    d.pay(2, 75_000)                                                       # one payment for two bills
    d.sale(60, 100_000)
    d.pay(61, 40_000)
    d.pay(62, 60_000)                                                      # one bill, two phones
    d.upload()
    b = d.block()
    assert (b["matched"]["grouped"], b["matched"]["split"], b["matched"]["count"], b["matched"]["sales"]) == (1, 1, 2, 3)
    assert b["sales_without_payment"]["count"] == 0 and b["payments_without_sale"]["count"] == 0


def test_a_sales_own_receipt_matches_it_and_a_wrong_amount_under_that_receipt_is_a_finding(db_session):
    d = Day(db_session)
    d.sale(0, 80_000, receipt="SJE4K2L9QA")
    d.pay(400, 80_000, receipt="SJE4K2L9QA")                              # hours later, but it is the same receipt
    d.sale(30, 50_000, receipt="SJE4K2LAB7")
    d.pay(31, 45_000, receipt="SJE4K2LAB7")
    d.upload()
    b = d.block()
    assert b["matched"]["receipt"] == 1 and b["different_amounts"] == [{"order_id": b["different_amounts"][0]["order_id"], "receipt": "SJE4K2LAB7", "sale_kes": 500.0, "payment_kes": 450.0}]
    assert "paid a different amount" in b["headline"] and b["sales_without_payment"]["count"] == 0


def test_sales_outside_the_days_the_statement_covers_are_counted_not_flagged(db_session):
    d = Day(db_session)
    d.sale(-3000, 100_000)                                                 # two days before the statement starts
    d.sale(0, 100_000)
    d.sale(30, 120_000)
    d.pay(1, 100_000)
    d.pay(31, 120_000)
    d.sale(5000, 130_000)                                                  # after it ends
    d.upload()
    b = d.block()
    assert b["sales_without_payment"]["count"] == 0 and b["outside_statement"] == {"sales": 2, "kes": 2300.0}
    assert b["headline"] == "All 2 M-Pesa sales match a payment on your statement."


def test_the_first_day_counts_from_midnight_but_the_last_ends_at_its_last_payment(db_session):
    """A statement is exported for whole days, so a sale early on its first day (before the first payment) is checked; it may have been
    exported at three o'clock, so a sale after its last payment is not accused of anything."""
    d = Day(db_session)
    d.sale(-60, 100_000)                                                   # 08:00, an hour before the first payment on the statement: checked, and missing
    d.sale(0, 110_000)
    d.pay(1, 110_000)
    d.sale(60, 120_000)
    d.pay(61, 120_000)
    d.sale(180, 130_000)                                                   # three hours after the last payment: the statement may simply be older
    d.upload()
    b = d.block()
    assert b["sales_without_payment"]["count"] == 1 and b["sales_without_payment"]["items"][0]["kes"] == 1000.0
    assert b["outside_statement"] == {"sales": 1, "kes": 1300.0} and b["window"]["from"] < d.base.isoformat()


def test_a_sale_whose_own_receipt_is_on_the_statement_is_checked_wherever_it_falls(db_session):
    d = Day(db_session)
    d.sale(-3000, 100_000, receipt="SJE4K2L9QA")                           # two days earlier than the rest of the statement
    d.pay(0, 100_000, receipt="SJE4K2L9QA")
    d.upload()
    assert d.block()["matched"]["receipt"] == 1


def test_only_paid_mpesa_sales_that_were_not_cancelled_count(db_session):
    d = Day(db_session)
    d.sale(0, 100_000)
    d.sale(10, 111_100, method=models.PaymentMethod.CASH)
    d.sale(20, 122_200, paid=False)
    d.sale(30, 133_300, status=models.OrderStatus.CANCELLED)
    d.sale(40, 0)
    d.sale(90, 140_000)                                                    # a real sale after them, so the days covered include all of the above
    d.pay(1, 100_000)
    d.pay(91, 140_000)
    d.upload()
    b = d.block()
    assert b["checked"]["sales"] == 2 and b["sales_without_payment"]["count"] == 0 and b["headline"] == "All 2 M-Pesa sales match a payment on your statement."


def test_the_time_of_a_sale_is_when_its_bill_closed(db_session):
    d = Day(db_session)
    order = d.sale(0, 100_000)
    order.completed_at = d.base + timedelta(minutes=50)                    # opened at 0, closed at 50
    db_session.commit()
    d.pay(52, 100_000)
    d.upload()
    assert d.block()["sales_without_payment"]["count"] == 0
    d2 = Day(db_session, suffix="m2")
    d2.sale(0, 100_000)                                                    # no closing time: it falls back to when it was opened
    d2.pay(2, 100_000)
    d2.upload()
    assert d2.block()["sales_without_payment"]["count"] == 0


def test_money_goes_out_of_the_statement_but_is_not_a_payment_to_explain(db_session):
    d = Day(db_session)
    d.sale(0, 100_000)
    d.pay(1, 100_000)
    d.upload()
    db_session.add(models.MpesaStatementLine(restaurant_id=d.g.rid, upload_id=db_session.query(models.MpesaStatementUpload).one().id, receipt="OUT0000001",
                                             completed_at=d.base + timedelta(minutes=5), paid_in_cents=0, withdrawn_cents=800_000, details="Business Payment"))
    db_session.commit()
    b = d.block()
    assert b["checked"]["payments"] == 1 and b["payments_without_sale"]["count"] == 0


def test_a_statement_not_updated_for_days_is_stale(db_session):
    d = Day(db_session, base=utcnow() - timedelta(days=5))
    d.sale(0, 100_000)
    d.pay(1, 100_000)
    d.upload()
    b = d.block()
    assert b["state"] == "stale" and b["source"] == "M-Pesa statement" and b["as_of"].startswith((utcnow() - timedelta(days=5)).strftime("%Y-%m-%d"))
    d2 = Day(db_session, suffix="m2", base=utcnow() - timedelta(days=2))
    d2.sale(0, 100_000)
    d2.pay(1, 100_000)
    d2.upload()
    assert d2.block()["state"] == "not_from_pos"


def test_the_minutes_are_the_owners_setting(db_session):
    d = Day(db_session)
    d.sale(0, 100_000)
    d.pay(12, 100_000)                                                     # twelve minutes after the bill closed
    d.upload()
    assert d.block()["sales_without_payment"]["count"] == 1                # the default is ten
    update_settings(db_session, d.g.rid, d.g.owner.id, {"mpesa_match_minutes": 15})
    b = d.block()
    assert b["sales_without_payment"]["count"] == 0 and b["assumption"]["value"] == 15
    update_settings(db_session, d.g.rid, d.g.owner.id, {"mpesa_match_minutes": 5})
    assert d.block()["sales_without_payment"]["count"] == 1


def test_another_restaurants_statement_and_sales_are_never_in_it(db_session):
    a = Day(db_session, suffix="ta")
    b = Day(db_session, suffix="tb")
    a.sale(0, 100_000)
    a.pay(1, 100_000)
    a.upload()
    b.sale(0, 999_900)
    b.sale(30, 888_800)
    b.pay(300, 555_500)
    b.upload()
    block_a, block_b = a.block(), b.block()
    assert block_a["checked"] == {"sales": 1, "payments": 1} and block_a["sales_without_payment"]["count"] == 0 and block_a["payments_without_sale"]["count"] == 0
    assert block_b["checked"]["payments"] == 1 and block_b["payments_without_sale"]["items"][0]["kes"] == 5555.0
    nobody = Day(db_session, suffix="tc")
    assert nobody.block()["state"] == "no_data"


# ── where it shows up ───────────────────────────────────────────────────────

def test_zone_1_carries_the_totals_and_the_cash_panel_the_lists(db_session):
    from owner.home import compose_home
    d = Day(db_session)
    for i in range(5):
        d.sale(i * 30, 100_000 + i * 5_000)
        if i != 3:
            d.pay(i * 30 + 2, 100_000 + i * 5_000)
    d.upload()
    home = compose_home(d.ctx(), "today")
    zone, panel = home["pulse"]["money_match"]["mpesa"], home["areas"]["cash"]["blocks"]["mpesa"]
    assert zone["headline"] == panel["headline"] and zone["state"] == panel["state"] == "not_from_pos"
    assert zone["sales_without_payment"] == {"count": 1, "kes": 1150.0} and zone["payments_without_sale"] == {"count": 0, "kes": 0.0}
    assert "items" not in zone["sales_without_payment"] and panel["sales_without_payment"]["items"][0]["kes"] == 1150.0
    assert zone["matched"] == panel["matched"] and zone["different_amounts"] == 0


def test_zone_1_without_a_statement_still_says_to_upload_one(db_session):
    from owner.home import compose_home
    d = Day(db_session)
    home = compose_home(d.ctx(), "today")
    assert home["pulse"]["money_match"]["mpesa"]["state"] == "no_data" and "Upload your M-Pesa statement" in home["pulse"]["money_match"]["mpesa"]["reason"]


def test_a_gap_is_one_more_thing_to_look_at_on_the_cash_panel(db_session):
    d = full_day(db_session, "cm")
    before = areas.cash_area(d.ctx())[0]["number"]
    d.sale(95, 321_000)
    after = areas.cash_area(d.ctx())[0]
    assert after["number"] == before + 1 and after["status"] == "bad"
    d.sale(96, 322_000)
    assert areas.cash_area(d.ctx())[0]["number"] == before + 1             # however many sales it spans, one thing to look at


def test_the_area_endpoint_returns_the_same_block(client, db_session):
    d = full_day(db_session, "ep")
    owner = d.g.owner
    h = {"Authorization": f"Bearer {auth.create_access_token({'sub': owner.email, 'ver': 0})}"}
    body = client.get("/api/v1/owner/area/cash", headers=h).json()
    assert body["blocks"]["mpesa"]["headline"] == d.block()["headline"] and body["blocks"]["mpesa"]["state"] == "not_from_pos"


def test_ask_levi_answers_an_mpesa_question_from_the_block(db_session):
    from owner import ask
    d = Day(db_session)
    for i in range(4):
        d.sale(i * 30, 100_000 + i * 7_000)
        if i != 1:
            d.pay(i * 30 + 1, 100_000 + i * 7_000)
    d.upload()
    out = ask.ask(d.ctx(), "Do my M-Pesa payments match my sales?")
    assert (out["form"], out["topic"], out["topic_label"]) == ("what", "mpesa", "M-Pesa check")
    assert out["state"] == "not_from_pos" and out["headline"] == "1 M-Pesa sale (KES 1,070) has no payment on your statement."
    assert ungrounded(out) == [] and any(r["key"] == "sales_without_payment" and r["value"] == 1 for r in out["rows"])
    assert any(a.get("setting") == "mpesa_match_minutes" for a in out["assumptions"])


def test_ask_levi_with_no_statement_says_what_to_do(db_session):
    from owner import ask
    d = Day(db_session)
    out = ask.ask(d.ctx(), "Does my M-Pesa statement agree with the till?")
    assert out["topic"] == "mpesa" and out["state"] == "no_data" and "Upload your M-Pesa statement" in out["reason"]


@pytest.mark.parametrize("question", ["Do my M-Pesa payments match my sales?", "Is any mpesa money missing?", "Check my statement", "Does the M Pesa statement agree?"])
def test_questions_about_mpesa_go_to_the_mpesa_topic(question):
    from owner import ask
    assert ask.classify(question) == ("what", "mpesa")


@pytest.mark.parametrize("period", ["weekly", "monthly"])
def test_the_weekly_and_monthly_reports_have_the_section_and_the_daily_does_not(db_session, period):
    from owner.reports import compose_report
    d = Day(db_session, "rp")
    for i in range(4):
        d.sale(i * 30, 100_000 + i * 7_000)
        if i != 2:
            d.pay(i * 30 + 1, 100_000 + i * 7_000)
    d.upload()
    section = next(s for s in compose_report(d.ctx(), period)["sections"] if s["key"] == "mpesa_check")
    assert section["state"] == "not_from_pos" and section["window"] == "The days your M-Pesa statement covers"
    assert section["headline"] == "1 M-Pesa sale (KES 1,140) has no payment on your statement." and ungrounded(section) == []
    assert section["source"] == "M-Pesa statement"
    assert not any(s["key"] == "mpesa_check" for s in compose_report(d.ctx(), "daily")["sections"])


def test_the_report_section_without_a_statement_says_why(db_session):
    from owner.reports import compose_report
    d = Day(db_session, "rq")
    section = next(s for s in compose_report(d.ctx(), "weekly")["sections"] if s["key"] == "mpesa_check")
    assert section["state"] == "no_data" and "Upload your M-Pesa statement" in section["reason"]


# ═════════════════════════════════════════════════════════════════════════════
# The setting and migration 056
# ═════════════════════════════════════════════════════════════════════════════

API = "/api/v1/owner/settings"


def _owner(db, suffix="a"):
    t = models.Tenant(name=f"T{suffix}")
    db.add(t)
    db.flush()
    r = models.Restaurant(tenant_id=t.id, name=f"R{suffix}", address="x")
    db.add(r)
    u = models.User(tenant_id=t.id, email=f"{suffix}@s62.test", hashed_password=auth.get_password_hash("x"), role=models.Role.STAFF,
                    staff_role=models.StaffRole.OWNER, token_version=0)
    db.add(u)
    db.commit()
    return r, u, {"Authorization": f"Bearer {auth.create_access_token({'sub': u.email, 'ver': 0})}"}


def test_the_minutes_setting_has_a_default_bounds_and_owner_words():
    from owner.settings import BY_KEY, DEFAULTS
    spec = BY_KEY["mpesa_match_minutes"]
    assert DEFAULTS.mpesa_match_minutes == 10 and (spec.group, spec.default, spec.minimum, spec.maximum, spec.unit) == ("Money", 10, 2, 60, "minutes")
    assert spec.question.endswith("?") and spec.label and spec.hint


def test_the_owner_can_set_the_minutes_and_it_is_audited(client, db_session):
    r, _u, h = _owner(db_session)
    assert client.put(API, headers=h, json={"mpesa_match_minutes": 20}).status_code == 200
    fields = {f["key"]: f for f in client.get(API, headers=h).json()["fields"]}
    assert fields["mpesa_match_minutes"]["value"] == 20 and not fields["mpesa_match_minutes"]["is_default"]
    assert db_session.query(models.RestaurantSettingsAudit).filter_by(field="mpesa_match_minutes").count() == 1


@pytest.mark.parametrize("payload", [{"mpesa_match_minutes": 1}, {"mpesa_match_minutes": 61}, {"mpesa_match_minutes": 7.5}, {"mpesa_match_minutes": "soon"}])
def test_out_of_range_minutes_are_refused(client, db_session, payload):
    _r, _u, h = _owner(db_session)
    assert client.put(API, headers=h, json=payload).status_code == 422 and db_session.query(models.RestaurantSettings).count() == 0


def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location("migration_056", BACKEND / "alembic" / "versions" / "056_add_mpesa_match_setting.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(conn, fn):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    module = _load()
    with Operations.context(MigrationContext.configure(conn)):
        getattr(module, fn)()


def test_migration_056_follows_055_and_the_chain_has_one_head():
    module = _load()
    assert module.down_revision == "055_mpesa_statements"
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    script = ScriptDirectory.from_config(config)
    assert len(script.get_heads()) == 1 and module.revision in {r.revision for r in script.walk_revisions()}


def test_migration_056_adds_the_column_with_a_default_to_an_existing_row_and_is_idempotent(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    with engine.begin() as conn:
        conn.execute(sa.text("create table restaurant_settings (id integer primary key, restaurant_id integer not null)"))
        conn.execute(sa.text("insert into restaurant_settings (id, restaurant_id) values (1, 7)"))
        _run(conn, "upgrade")
        assert conn.execute(sa.text("select mpesa_match_minutes from restaurant_settings")).scalar() == 10         # the row written before it reads as the default
        _run(conn, "upgrade")                                                                                         # create_all() may have added it already
        _run(conn, "downgrade")
        assert "mpesa_match_minutes" not in {c["name"] for c in sa.inspect(conn).get_columns("restaurant_settings")}
        _run(conn, "downgrade")


def test_migration_056_renders_postgresql_ddl_offline():
    env = {**os.environ, "DATABASE_URL": "postgresql+psycopg2://offline:offline@localhost:5432/offline", "SECRET_KEY": "x"}
    up = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "055_mpesa_statements:056_mpesa_match_setting", "--sql"],
                        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
    assert up.returncode == 0, up.stderr[-1500:]
    assert "ADD COLUMN mpesa_match_minutes INTEGER DEFAULT '10' NOT NULL" in up.stdout or "mpesa_match_minutes INTEGER" in up.stdout
    down = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "056_mpesa_match_setting:055_mpesa_statements", "--sql"],
                          cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
    assert down.returncode == 0, down.stderr[-1500:]
    assert "DROP COLUMN mpesa_match_minutes" in down.stdout
