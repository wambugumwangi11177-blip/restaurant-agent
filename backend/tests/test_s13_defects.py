"""
S1.3 — verified defects D1, D3, D10, D12, D15, D16 (docs/v2/SPEC.md §1.5) plus D17 (func.date over UTC columns,
found in S0.2). One regression test per defect, written before the fix and red for the right reason.
"""
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

import models
from time_utils import utcnow
from tests.fixtures import golden_restaurant as gr

DATA = Path(__file__).resolve().parents[1] / "data"


# ═════════════════════════════════════════════════════════════════════════════
# D1 — a missing M-Pesa receipt is only suspicious on LEVIII's own STK path
# ═════════════════════════════════════════════════════════════════════════════

def _mpesa_orders(db, g, count, *, stk: bool, start=0):
    for i in range(count):
        o = models.Order(
            restaurant_id=g.rid, status=models.OrderStatus.SERVED, payment_method=models.PaymentMethod.MPESA,
            is_paid=True, total=50_000, created_at=g.now - timedelta(hours=1, minutes=i), mpesa_receipt=None,
            mpesa_checkout_request_id=f"ws_CO_{start + i}" if stk else None,
        )
        db.add(o)
    db.commit()


def test_d1_pos_fed_orders_without_receipts_are_not_a_payment_mismatch(db_session):
    from ai.fraud.detection import compute_fraud_report
    from ai.cash_reconciliation.intelligence import compute_reconciliation_report
    g = gr.build_skeleton(db_session)
    _mpesa_orders(db_session, g, 40, stk=False)                  # a POS feed that never carries receipts
    assert compute_fraud_report(db_session, g.rid).payment_mismatches == []
    assert compute_reconciliation_report(db_session, g.rid).mpesa_mismatches == []


def test_d1_an_stk_order_marked_paid_with_no_receipt_is_still_flagged(db_session):
    from ai.fraud.detection import compute_fraud_report
    g = gr.build_skeleton(db_session)
    _mpesa_orders(db_session, g, 3, stk=True)
    _mpesa_orders(db_session, g, 5, stk=False, start=100)
    flags = compute_fraud_report(db_session, g.rid).payment_mismatches
    assert len(flags) == 3                                       # only the STK ones


def test_d1_home_shows_one_summary_card_not_one_per_order(db_session):
    from ai.home_specialists import collect
    g = gr.build_skeleton(db_session)
    _mpesa_orders(db_session, g, 12, stk=True)
    cards, _states = collect(db_session, g.rid)
    payment = [c for c in cards if c["domain"] == "Payment review"]
    assert len(payment) == 1
    assert "12" in payment[0]["title"]
    assert "not prove" in payment[0]["why"].lower() or "does not prove" in payment[0]["why"].lower()


# ═════════════════════════════════════════════════════════════════════════════
# D3 — a supplier's reliability: no writes in a read, and "learning" until 3 closed orders
# ═════════════════════════════════════════════════════════════════════════════

def _po(db, g, status, *, days_ago=5, supplier=None):
    po = models.PurchaseOrder(
        restaurant_id=g.rid, supplier_id=(supplier or g.supplier).id, inventory_item_id=g.inventory["Beef"].id,
        quantity_ordered=10.0, quantity_received=10.0 if status in ("DELIVERED", "LATE") else None, unit="kg",
        cost_per_unit=80_000, total_cost=800_000, status=status, ordered_at=g.now - timedelta(days=days_ago),
        expected_at=g.now - timedelta(days=days_ago - 1),
        delivered_at=g.now - timedelta(days=days_ago - 1) if status in ("DELIVERED", "LATE") else None)
    db.add(po)
    db.commit()
    return po


def _supplier_row(db, g):
    from ai.supply_chain.intelligence import get_supply_chain_intelligence
    return get_supply_chain_intelligence(db, g.rid)["suppliers"][0]


def test_d3_reading_supplier_intelligence_never_writes(db_session):
    g = gr.build_skeleton(db_session)
    for status in ("DELIVERED", "LATE", "LATE", "DELIVERED"):
        _po(db_session, g, status)
    row = _supplier_row(db_session, g)
    assert row["reliability_score"] == 50.0
    assert not db_session.dirty                                   # nothing was touched in the session
    db_session.commit()
    db_session.expire_all()
    assert db_session.get(models.Supplier, g.supplier.id).reliability_score == 100.0     # and nothing was stored


def test_d3_one_delivered_order_is_learning_not_100_percent_reliable(db_session):
    g = gr.build_skeleton(db_session)
    _po(db_session, g, "DELIVERED")
    row = _supplier_row(db_session, g)
    assert row["reliability_label"] == "LEARNING" and row["reliability_score"] is None
    assert row["closed_orders"] == 1 and row["at_risk"] is False
    from ai.supply_chain.intelligence import get_supply_chain_intelligence
    data = get_supply_chain_intelligence(db_session, g.rid)
    assert data["summary"]["at_risk_suppliers"] == 0 and data["summary"]["avg_reliability_pct"] is None


def test_d3_three_closed_orders_make_a_real_score(db_session):
    g = gr.build_skeleton(db_session)
    for status in ("DELIVERED", "DELIVERED", "LATE"):
        _po(db_session, g, status)
    row = _supplier_row(db_session, g)
    assert row["reliability_score"] == pytest.approx(66.7, abs=0.05) and row["reliability_label"] == "POOR"
    assert row["closed_orders"] == 3 and row["at_risk"] is True


def test_d3_receiving_a_purchase_order_is_where_the_stored_score_is_refreshed(db_session):
    from ai.reorder import receive_purchase_order
    g = gr.build_skeleton(db_session)
    for status in ("LATE", "LATE", "DELIVERED"):
        _po(db_session, g, status)
    sent = _po(db_session, g, "SENT", days_ago=1)
    assert db_session.get(models.Supplier, g.supplier.id).reliability_score == 100.0
    receive_purchase_order(db_session, sent.id, g.rid, 10.0, g.storekeeper.id)
    db_session.expire_all()
    assert db_session.get(models.Supplier, g.supplier.id).reliability_score == 50.0      # 2 of 4 on time


def test_d3_the_stored_score_stays_put_while_a_supplier_is_still_learning(db_session):
    from ai.reorder import receive_purchase_order
    g = gr.build_skeleton(db_session)
    sent = _po(db_session, g, "SENT", days_ago=1)
    receive_purchase_order(db_session, sent.id, g.rid, 10.0, g.storekeeper.id)
    db_session.expire_all()
    assert db_session.get(models.Supplier, g.supplier.id).reliability_score == 100.0     # 1 closed order: not enough to judge


# ═════════════════════════════════════════════════════════════════════════════
# D10 — overtime cost counts the overtime hours, not the whole shift
# ═════════════════════════════════════════════════════════════════════════════

def test_d10_overtime_cost_is_overtime_hours_times_the_hourly_rate(db_session):
    from ai.labor.intelligence import get_labor_intelligence
    g = gr.build_skeleton(db_session)
    gr.seed_overtime_shift(db_session, g, hours=10.0)            # KES 125/h → the shift cost KES 1,250
    summary = get_labor_intelligence(db_session, g.rid)["summary"]
    assert summary["overtime_hours_30d"] == 2.0
    assert summary["overtime_cost_30d"] == 25_000                # 2 h × KES 125, not the whole KES 1,250
    assert summary["total_labor_cost_30d"] == 125_000


# ═════════════════════════════════════════════════════════════════════════════
# D12 — holidays come from a yearly data file, 2026 and 2027
# ═════════════════════════════════════════════════════════════════════════════

def _reasons(d):
    from ai.simulation.signals import demand_signals
    return demand_signals(d)["reasons"]


def test_d12_2026_holidays_are_unchanged():
    assert any("Christmas Day" in r for r in _reasons(date(2026, 12, 25)))
    assert any("Eid al-Fitr" in r for r in _reasons(date(2026, 3, 20)))
    assert _reasons(date(2026, 7, 14)) == []


def test_d12_2027_holidays_exist_including_sunday_observed_mondays():
    assert any("New Year" in r for r in _reasons(date(2027, 1, 1)))
    assert any("Good Friday" in r for r in _reasons(date(2027, 3, 26)))
    assert any("Easter Monday" in r for r in _reasons(date(2027, 3, 29)))
    assert any("Madaraka" in r for r in _reasons(date(2027, 6, 1)))
    assert any("Mashujaa" in r for r in _reasons(date(2027, 10, 20)))
    # 10 Oct, 12 Dec and 26 Dec 2027 fall on Sundays: the Monday after is the public holiday.
    assert date(2027, 10, 10).weekday() == 6 and any("Huduma" in r for r in _reasons(date(2027, 10, 11)))
    assert date(2027, 12, 12).weekday() == 6 and any("Jamhuri" in r for r in _reasons(date(2027, 12, 13)))
    assert date(2027, 12, 26).weekday() == 6 and any("Utamaduni" in r for r in _reasons(date(2027, 12, 27)))


def test_d12_a_year_without_a_file_is_neutral_not_an_error():
    from ai.simulation.signals import demand_signals
    signal = demand_signals(date(2031, 12, 25))
    assert signal["factor"] == 1.0 and signal["reasons"] == []


@pytest.mark.parametrize("year", [2026, 2027])
def test_d12_the_data_files_are_well_formed(year):
    doc = json.loads((DATA / f"ke_holidays_{year}.json").read_text())
    assert doc["year"] == year and doc["country"] == "KE" and doc["source_note"]
    seen = set()
    for h in doc["public_holidays"]:
        d = date.fromisoformat(h["date"])
        assert d.year == year and h["name"] and d not in seen
        seen.add(d)
    for window in doc.get("school_breaks", []):
        assert date.fromisoformat(window["start"]) <= date.fromisoformat(window["end"])


def test_d12_the_2026_constants_are_gone_from_code():
    from ai.simulation import signals
    assert not hasattr(signals, "KENYA_PUBLIC_HOLIDAYS_2026") and not hasattr(signals, "SCHOOL_BREAK_WINDOWS_2026")


# ═════════════════════════════════════════════════════════════════════════════
# D15 — "portion drift" is really sales below the menu price
# ═════════════════════════════════════════════════════════════════════════════

def test_d15_profit_reports_till_price_gap_and_keeps_portion_drift_as_a_deprecated_alias(db_session):
    from ai.profit.intelligence import get_profit_intelligence
    g = gr.build_skeleton(db_session)
    gr.seed_chips_below_menu(db_session, g)
    data = get_profit_intelligence(db_session, g.rid)
    gap = data["till_price_gap"]
    assert gap and gap[0]["item_name"] == "Chips" and gap[0]["estimated_monthly_leak"] == 2_571_428
    assert data["portion_drift"] == gap                                              # deprecated alias, same rows
    rec = next(r for r in data["recommendations"] if r["type"] == "till_price_gap")
    assert "below menu price" in rec["message"]
    assert "staff may be" not in gap[0]["action"].lower()                            # a signal, never a verdict


def test_d15_the_roi_total_reads_the_new_key(db_session):
    from ai.roi.savings import get_roi_savings
    g = gr.build_skeleton(db_session)
    gr.seed_chips_below_menu(db_session, g)
    text = json.dumps(get_roi_savings(db_session, g.rid), default=str)
    assert "2571428" in text or "25714" in text


# ═════════════════════════════════════════════════════════════════════════════
# D16 — suggested prices round to a menu-friendly KES step, not KES 0.50
# ═════════════════════════════════════════════════════════════════════════════

def test_d16_cost_26000_cents_suggests_43500():
    from ai.pricing.analysis import _round_price_up
    assert _round_price_up(26_000 / (1 - 0.40)) == 43_500                           # KES 435, not 433.50


def test_d16_rounding_follows_the_step_and_reprice_always_rounds_up():
    from ai.pricing.analysis import _round_price, _round_price_up
    assert _round_price_up(43_333.33, 500) == 43_500 and _round_price_up(43_000.0, 500) == 43_000
    assert _round_price_up(43_333.33, 100) == 43_400 and _round_price_up(43_333.33, 1_000) == 44_000
    assert _round_price(43_240, 500) == 43_000 and _round_price(43_260, 500) == 43_500   # nearest, for SURGE/STIMULATE
    assert _round_price(120, 500) == 500 and _round_price_up(10, 500) == 500             # never below one step


def test_d16_the_owners_price_step_changes_the_suggestion(db_session):
    from ai.pricing.recommendations import get_pricing_intelligence
    from owner.settings import update_settings
    g = gr.build_skeleton(db_session)
    gr.seed_chicken_reprice(db_session, g)
    price = lambda: next(r for r in get_pricing_intelligence(db_session, g.rid)["recommendations"]
                         if r["item_name"] == "Quarter chicken")["suggested_price"]
    assert price() == 43_500
    update_settings(db_session, g.rid, g.owner.id, {"price_step_kes": 1})
    assert price() == 43_400
    update_settings(db_session, g.rid, g.owner.id, {"price_step_kes": 10})
    assert price() == 44_000


def test_d16_reprice_never_lands_below_the_floor_at_any_step():
    from ai.pricing.analysis import _round_price_up
    for step in (100, 500, 1_000, 5_000):
        for cost in range(1_000, 80_000, 337):
            price = _round_price_up(cost / 0.6, step)
            assert price % step == 0 and (price - cost) / price * 100 >= 40.0 - 1e-9


# ═════════════════════════════════════════════════════════════════════════════
# D17 — the owner's day is the Nairobi day (no func.date over UTC columns)
# ═════════════════════════════════════════════════════════════════════════════

def test_d17_labour_daily_revenue_is_bucketed_by_the_nairobi_day(db_session):
    from ai.labor.intelligence import get_labor_intelligence
    g = gr.build_skeleton(db_session)
    utc_day = (g.now - timedelta(days=3)).date()
    pilau = g.items["Pilau"]
    for k in range(5):                                           # 21:30 UTC = 00:30 the NEXT day in Nairobi
        gr.add_order(db_session, g, [(pilau, 1, pilau.price)], datetime.combine(utc_day, datetime.min.time()) + timedelta(hours=21, minutes=30 + k))
    member = models.StaffMember(restaurant_id=g.rid, name="A", hourly_rate=12_500)
    db_session.add(member)
    db_session.flush()
    for offset in (utc_day, utc_day + timedelta(days=1)):
        db_session.add(models.LaborShift(restaurant_id=g.rid, staff_member_id=member.id, shift_date=offset,
                                         scheduled_hours=8.0, actual_hours=8.0, labor_cost=100_000))
    db_session.commit()
    rows = {r["date"]: r for r in get_labor_intelligence(db_session, g.rid)["daily_breakdown"]}
    assert rows[str(utc_day + timedelta(days=1))]["revenue"] == 5 * pilau.price          # the Nairobi date
    assert rows[str(utc_day)]["revenue"] == 0


def test_d17_void_spike_baseline_counts_days_the_way_the_owner_does(db_session):
    """Four audits at 20:30 UTC and four at 21:30 UTC each day (23:30 and 00:30 in Nairobi). By UTC date that is
    8 a day; by Nairobi date it is 4, 8, 8, ... 8, 4 — a wider spread, so a window of 10 is NOT a spike."""
    from ai.fraud.detection import compute_fraud_report
    g = gr.build_skeleton(db_session)
    o = gr.add_order(db_session, g, [(g.items["Pilau"], 1, 35_000)], g.now - timedelta(days=40))
    db_session.commit()
    midnight = datetime.combine((g.now - timedelta(days=20)).date(), datetime.min.time())
    for day in range(8):
        for hour_minute in ((20, 30), (21, 30)):
            for k in range(4):
                db_session.add(models.OrderAudit(order_id=o.id, restaurant_id=g.rid, action=models.OrderAuditAction.CANCEL,
                                                 actor_user_id=g.manager.id,
                                                 created_at=midnight + timedelta(days=day, hours=hour_minute[0], minutes=hour_minute[1] + k)))
    for k in range(10):
        db_session.add(models.OrderAudit(order_id=o.id, restaurant_id=g.rid, action=models.OrderAuditAction.CANCEL,
                                         actor_user_id=g.manager.id, created_at=g.now - timedelta(minutes=5 + k)))
    db_session.commit()
    assert compute_fraud_report(db_session, g.rid).void_spikes == []
