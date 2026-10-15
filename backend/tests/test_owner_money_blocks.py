"""
S3.3 — the money blocks on Home (owner/areas.py): costs covered, bill radar, costs going up, licences, the coming-up lists, and the
pulse chip. Built on a context whose clock is pinned, so a number never depends on what time the test runs.
"""
from datetime import date, datetime, timedelta

import pytest

import models
from owner import areas
from owner.home import compose_home
from owner.states import OwnerContext
from tests.fixtures import golden_restaurant as gr

NOW = datetime(2026, 10, 3, 9, 30)                  # Saturday 12:30 in Nairobi; September is the last complete month
SEPT = datetime(2026, 9, 25, 10, 0)


def _ctx(db, g, now=NOW):
    ctx = OwnerContext(db, g.owner, g.restaurant)
    ctx.now = now
    return ctx


def _month_g(db):
    g = gr.build_skeleton(db, now=SEPT)
    gr.seed_pnl_month(db, g)
    return g


# ── costs covered ────────────────────────────────────────────────────────────

def test_hhmm_is_nairobi_wall_clock():
    assert areas._hhmm(datetime(2026, 10, 3, 12, 40)) == "3:40 pm"
    assert areas._hhmm(datetime(2026, 10, 3, 6, 0)) == "9:00 am"
    assert areas._hhmm(datetime(2026, 10, 3, 9, 5)) == "12:05 pm"
    assert areas._hhmm(datetime(2026, 10, 3, 21, 0)) == "12:00 am"                 # midnight Nairobi


def test_costs_covered_before_the_line_says_how_much_is_to_go(db_session):
    g = _month_g(db_session)
    pilau = g.items["Pilau"]
    gr.add_order(db_session, g, [(pilau, 10, 35_000)], datetime(2026, 10, 3, 6, 0))          # 09:00 in Nairobi: KES 3,500
    db_session.commit()
    b = areas.breakeven_summary(_ctx(db_session, g))
    assert b["state"] == "live"
    assert (b["break_even_kes"], b["sales_today_kes"], b["to_go_kes"], b["covered"], b["crossed_at"]) == (9_534.31, 3_500.0, 6_034.31, False, None)
    assert (b["fixed_per_day_kes"], b["food_cost_pct"]) == (6_483.33, 32.0)
    assert b["built_from"]["label"] == "September 2026" and b["built_from"]["period"] == "last_month" and b["built_from"]["days"] == 30
    assert b["built_from"]["fixed_costs_kes"] == 194_500.0 and b["built_from"]["wages_kes"] == 103_000.0
    assert {l["name"] for l in b["built_from"]["lines"]} == {"Rent & premises", "Electricity (KPLC)", "Water", "Security", "Licences & permits"}
    assert "move with sales" in b["note"] and b["assumption"]["setting"] == "food_cost_target_pct"


def test_costs_covered_after_the_line_says_when(db_session):
    g = _month_g(db_session)
    pilau = g.items["Pilau"]
    for hour in (6, 8, 9, 11):
        gr.add_order(db_session, g, [(pilau, 10, 35_000)], datetime(2026, 10, 3, hour, 0))
    db_session.commit()
    b = areas.breakeven_summary(_ctx(db_session, g, now=datetime(2026, 10, 3, 12, 0)))
    assert b["covered"] is True and b["crossed_at"] == "12:00 pm" and b["to_go_kes"] == 0.0 and b["sales_today_kes"] == 14_000.0       # 3,500 × 3 = 10,500 ≥ 9,534


def test_costs_covered_is_no_data_until_there_are_costs_and_sales(db_session):
    g = gr.build_skeleton(db_session, now=SEPT)
    b = areas.breakeven_summary(_ctx(db_session, g))
    assert b["state"] == "no_data" and "enter your costs" in b["reason"].lower()


def test_the_pulse_chip_is_the_same_summary(db_session):
    g = _month_g(db_session)
    pilau = g.items["Pilau"]
    gr.add_order(db_session, g, [(pilau, 4, 35_000)], datetime(2026, 10, 3, 7, 0))
    db_session.commit()
    ctx = _ctx(db_session, g)
    home = compose_home(ctx, "today")
    strip = lambda b: {k: v for k, v in b.items() if k != "as_of"}                               # noqa: E731
    assert strip(home["pulse"]["breakeven_at"]) == strip(areas.breakeven_summary(ctx)) == strip(home["areas"]["money"]["blocks"]["breakeven"])
    assert home["areas"]["money"]["blocks"]["breakeven"]["break_even_kes"] == home["pulse"]["breakeven_at"]["break_even_kes"] == 9_534.31


# ── bill radar ───────────────────────────────────────────────────────────────

def _bill(db, g, name, cents, due_day, key="premises"):
    from owner.money.categories import ensure_categories
    ensure_categories(db, g.rid)
    cat = db.query(models.ExpenseCategory).filter_by(restaurant_id=g.rid, key=key).one()
    db.add(models.RecurringBill(restaurant_id=g.rid, category_id=cat.id, name=name, amount_cents=cents, frequency="monthly", due_day=due_day,
                                start_on=date(2026, 1, 1), supplier="", note="", is_active=True))
    db.commit()


@pytest.fixture
def flat_forecast(monkeypatch):
    import owner.money.radar as radar
    monkeypatch.setattr(radar, "forecast_sales", lambda db, rid, today, horizon=30: {today + timedelta(days=i): 1_500_000 for i in range(horizon)})


def test_the_radar_block_speaks_shillings_and_names_the_shortfall(db_session, flat_forecast):
    g = _month_g(db_session)
    _bill(db_session, g, "Rent", 7_000_000, 6)                      # three days from the 3rd
    b = areas.bills_block(_ctx(db_session, g))
    assert b["state"] == "as_entered" and b["opening_kes"] == 0.0 and len(b["days"]) == 30
    assert b["assumption"] == {"setting": "bill_reserve_kes", "value": 0, "label": "Cash you keep aside for bills"}
    (rent,) = b["upcoming"]
    assert (rent["name"], rent["due_on"], rent["days_away"], rent["amount_kes"], rent["short"]) == ("Rent", "2026-10-06", 3, 70_000.0, True)
    assert b["shortfalls"][0]["date"] == "2026-10-06" and b["shortfalls"][0]["bills"] == ["Rent"] and b["shortfalls"][0]["short_by_kes"] > 0
    assert b["days"][0]["expected_sales_kes"] == 15_000.0 and b["days"][3]["bills_kes"] == 70_000.0
    assert b["lowest"]["date"] == "2026-10-06" and b["lowest"]["balance_kes"] < 0
    assert not any("cents" in k for d in b["days"] for k in d)
    assert any("after ingredients and wages" in n for n in b["notes"])


def test_cash_set_aside_removes_the_shortfall(db_session, flat_forecast):
    from owner.settings import update_settings
    g = _month_g(db_session)
    _bill(db_session, g, "Rent", 7_000_000, 6)
    update_settings(db_session, g.rid, g.owner.id, {"bill_reserve_kes": 60_000})
    b = areas.bills_block(_ctx(db_session, g))
    assert b["opening_kes"] == 60_000.0 and b["shortfalls"] == [] and b["upcoming"][0]["short"] is False
    assert b["assumption"]["value"] == 60_000


def test_the_radar_block_says_why_it_has_nothing(db_session, monkeypatch):
    g = _month_g(db_session)
    assert areas.bills_block(_ctx(db_session, g)) == {"state": "no_data", "as_of": None, "reason": "No bills entered yet."}
    _bill(db_session, g, "Rent", 7_000_000, 6)
    import owner.money.radar as radar
    monkeypatch.setattr(radar, "forecast_sales", lambda *a, **k: None)
    b = areas.bills_block(_ctx(db_session, g))
    assert b["state"] == "no_data" and "two weeks of sales" in b["reason"]


def test_the_coming_up_bills_are_the_next_two_weeks(db_session, flat_forecast):
    g = _month_g(db_session)
    _bill(db_session, g, "Rent", 7_000_000, 6)
    _bill(db_session, g, "KPLC", 1_800_000, 20, key="kplc")
    b = areas.bills_due_block(_ctx(db_session, g))
    assert [(i["name"], i["days_away"], i["amount_kes"]) for i in b["items"]] == [("Rent", 3, 70_000.0)]            # the 20th is 17 days away
    assert areas.bills_due_block(_ctx(db_session, g), days=30)["items"][1]["name"] == "KPLC"
    quiet = gr.build_skeleton(db_session, now=SEPT, suffix="quiet")
    assert areas.bills_due_block(_ctx(db_session, quiet))["state"] == "no_data"


# ── costs going up ───────────────────────────────────────────────────────────

def test_the_spikes_block(db_session):
    g = gr.build_skeleton(db_session, now=SEPT)
    ctx = _ctx(db_session, g, now=datetime(2026, 10, 12, 9, 0))
    assert areas.spikes_block(ctx)["state"] == "no_data"
    for i, cents in enumerate((1_460_000, 1_410_000, 1_430_000)):
        gr.seed_expenses(db_session, g, [("gas", cents)], paid_on=date(2026, 7 + i, 14))
    b = areas.spikes_block(ctx)
    assert b["state"] == "as_entered" and b["spikes"] == [] and b["reason"] == "Nothing is costing more than usual."       # 91 days of history, this month still empty
    gr.seed_expenses(db_session, g, [("gas", 1_860_000)], paid_on=date(2026, 10, 5))
    b = areas.spikes_block(ctx)
    assert b["state"] == "as_entered" and b["reason"] is None
    assert b["spikes"] == [{"name": "Cooking gas", "this_month_kes": 18_600.0, "usual_kes": 14_333.33, "up_pct": 29.8, "extra_kes": 4_266.67}]
    assert b["assumption"] == {"setting": "expense_spike_pct", "value": 25.0, "label": "Cost increase we flag"}
    calm = gr.build_skeleton(db_session, now=SEPT, suffix="calm")
    for i, cents in enumerate((1_460_000, 1_410_000, 1_430_000)):
        gr.seed_expenses(db_session, calm, [("gas", cents)], paid_on=date(2026, 7 + i, 14))
    gr.seed_expenses(db_session, calm, [("gas", 1_000_000)], paid_on=date(2026, 10, 5))
    b = areas.spikes_block(_ctx(db_session, calm, now=datetime(2026, 10, 12, 9, 0)))
    assert b["spikes"] == [] and b["reason"] == "Nothing is costing more than usual."


def test_the_spikes_block_is_learning_before_there_are_three_months(db_session):
    g = gr.build_skeleton(db_session, now=SEPT)
    gr.seed_expenses(db_session, g, [("gas", 1_400_000)], paid_on=date(2026, 9, 20))
    b = areas.spikes_block(_ctx(db_session, g, now=datetime(2026, 10, 12, 9, 0)))
    assert b["state"] == "learning" and (b["day"], b["of"]) == (23, 90) and "three months" in b["reason"]


# ── licences ─────────────────────────────────────────────────────────────────

def _licence(db, g, name, days_from_now, now=NOW):
    db.add(models.Licence(restaurant_id=g.rid, name=name, issuer="County", expires_on=(now + timedelta(hours=3)).date() + timedelta(days=days_from_now),
                          is_active=True, note=""))
    db.commit()


def test_licences_in_owner_words_and_the_ones_due_soon(db_session):
    g = gr.build_skeleton(db_session, now=SEPT)
    ctx = _ctx(db_session, g)
    assert areas.licences_block(ctx)["state"] == "no_data" and areas.licences_due_block(ctx)["state"] == "no_data"
    for name, days in (("Health certificate", 10), ("Fire certificate", -2), ("Single business permit", 200), ("Liquor licence", 14), ("Music licence", 15)):
        _licence(db_session, g, name, days)
    all_ = areas.licences_block(ctx)
    assert all_["state"] == "as_entered" and [(i["name"], i["word"]) for i in all_["items"]] == [
        ("Fire certificate", "Expired"), ("Health certificate", "Expires soon"), ("Liquor licence", "Expires soon"), ("Music licence", "Fine"), ("Single business permit", "Fine")]
    assert all_["assumption"] == {"setting": "licence_warning_days", "value": 14, "label": "Licence warning (days)"}
    due = areas.licences_due_block(ctx)
    assert [i["name"] for i in due["items"]] == ["Fire certificate", "Health certificate", "Liquor licence"] and due["reason"] is None
    far = gr.build_skeleton(db_session, now=SEPT, suffix="far")
    _licence(db_session, far, "Permit", 300)
    quiet = areas.licences_due_block(_ctx(db_session, far))
    assert quiet["state"] == "as_entered" and quiet["items"] == [] and quiet["reason"] == "Nothing expires in the next 14 days."


# ── the coming-up bookings ───────────────────────────────────────────────────

def test_a_quiet_evening_still_shows_the_days_ahead(db_session):
    from owner.home import _bookings
    g = gr.build_skeleton(db_session, now=SEPT)
    from datetime import time as _t

    def book(day, hour, size, status=models.ReservationStatus.CONFIRMED):
        db_session.add(models.Reservation(restaurant_id=g.rid, customer_name="Guest", party_size=size, reservation_date=day, reservation_time=_t(hour, 0), status=status))
    today = date(2026, 10, 3)
    book(today, 11, 4)                                              # this morning: already over at 12:30
    book(today, 19, 6)                                              # tonight
    book(today + timedelta(days=1), 13, 2)
    book(today + timedelta(days=1), 20, 5)
    book(today + timedelta(days=3), 19, 8)
    book(today + timedelta(days=2), 19, 3, status=models.ReservationStatus.CANCELLED)
    book(today + timedelta(days=9), 19, 9)                          # beyond the week
    db_session.commit()
    b = _bookings(_ctx(db_session, g), covers_today=10)
    assert b["state"] == "live" and b["covers_today"] == 10
    assert b["next_days"] == [{"date": "2026-10-03", "bookings": 1, "covers": 6}, {"date": "2026-10-04", "bookings": 2, "covers": 7}, {"date": "2026-10-06", "bookings": 1, "covers": 8}]
    late = _bookings(_ctx(db_session, g, now=datetime(2026, 10, 3, 19, 0)), covers_today=0)             # 22:00 in Nairobi: tonight is over
    assert late["state"] == "live" and late["reason"] == "No bookings tonight." and late["next_days"][0]["date"] == "2026-10-04"
    nothing = gr.build_skeleton(db_session, now=SEPT, suffix="none")
    assert _bookings(_ctx(db_session, nothing), covers_today=0)["state"] == "no_data"


def test_the_money_blocks_survive_an_engine_failure(db_session, monkeypatch):
    g = _month_g(db_session)
    import owner.money.breakeven as be
    monkeypatch.setattr(be, "break_even", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    home = compose_home(_ctx(db_session, g), "today")
    assert home["areas"]["money"]["blocks"]["breakeven"]["state"] == "unavailable"
    assert home["pulse"]["breakeven_at"]["state"] == "unavailable" and "boom" not in str(home)
    assert home["areas"]["money"]["blocks"]["pnl"]["state"] == "no_data"                            # the rest of the area is untouched (October has no sales yet)
