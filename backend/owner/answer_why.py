"""
backend/owner/answer_why.py — the "why" form: why was that day bad? (docs/v2/SPEC.md §4 P5.1, scenario P12)

A day's sales are set beside a usual day of the same weekday (the average of the seven before it), and then the records are
searched for the drivers the spec names, IN THIS ORDER:

    1. holiday      the calendar says it was a public holiday / school holiday (ai/simulation/signals.py — the same signal the forecast uses)
    2. stock_out    a dish that usually sells late stopped selling while the restaurant kept trading
    3. staffing     fewer staff hours than a usual day
    4. cancelled_sales   cancelled sales well above usual

Every driver is listed with whether it was found; one that was not found says what was checked ("nothing unusual"), or that there was
nothing recorded to check. A day with no sales is not explained, and an ordinary day is not given a cause: signals, not verdicts.

The four tests below are heuristics of this module, not owner rules (an owner cannot sensibly "set" them): they are shown to the owner
in the answer's assumptions, and live together in WHY so they are not scattered.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import func

import models
from owner.answers import assumption, clock_text, day_text, kes_text, make, nothing, pct_text, row
from owner.money.pnl import nairobi_utc_range
from owner.states import OwnerContext
from time_utils import EAT_OFFSET, service_day, trading_day, trading_window

WHY = SimpleNamespace(
    usual_days=7,            # the usual day = the average of this many earlier days of the same weekday …
    min_usual=3,             # … of which at least this many must have sales, or "usual" is not known yet
    keep_trading=timedelta(minutes=60),   # a dish "ran out" only if the restaurant still took orders at least this long after the shelf was empty
    staff_share=0.75,        # fewer staff hours than this share of a usual day is "fewer staff"
    cancel_multiple=2.0,     # cancelled sales at least this many times a usual day's …
    min_cancelled=3,         # … and at least this many of them
)
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
_MONTH = "|".join(MONTHS)


def _past(month: int, day: int, today: date) -> date | None:
    """The latest date with this month and day that is not in the future (this year, else last year)."""
    for year in (today.year, today.year - 1):
        try:
            d = date(year, month, day)
        except ValueError:
            continue
        if d <= today:
            return d
    return None


def parse_day(question: str, today: date) -> date:
    """The day the owner means: "2026-10-20", "20 Oct", "Oct 20", "the 20th", "yesterday", "today", "Tuesday last week", or a weekday (the
    latest one that is over). Yesterday if none is named."""
    q = question.lower()
    iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", q)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            pass
    dm = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH})[a-z]*\b", q)
    md = re.search(rf"\b({_MONTH})[a-z]*\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", q)
    if dm or md:
        day, month = (int(dm.group(1)), MONTHS[dm.group(2)]) if dm else (int(md.group(2)), MONTHS[md.group(1)])
        found = _past(month, day, today)
        if found:
            return found
    nth = re.search(r"\bthe\s+(\d{1,2})(?:st|nd|rd|th)\b", q)
    if nth:
        want = int(nth.group(1))
        for back in range(0, 62):
            d = today - timedelta(days=back)
            if d.day == want and d < today:
                return d
    if "yesterday" in q:
        return today - timedelta(days=1)
    if re.search(r"\btoday\b", q):
        return today
    for i, name in enumerate(WEEKDAYS):
        if re.search(rf"\b{name}s?\b", q):
            if "last week" in q:
                return today - timedelta(days=today.weekday()) - timedelta(days=7 - i)
            back = (today.weekday() - i) % 7 or 7
            return today - timedelta(days=back)
    return today - timedelta(days=1)


def _day_window(day: date) -> tuple[datetime, datetime]:
    return nairobi_utc_range(day, day)


def _sales(ctx: OwnerContext, day: date) -> tuple[float, int]:
    # The open service day uses the same window as "how were sales today?" (midnight through now,
    # rolling at 06:00). A named earlier day stays the full Nairobi calendar day.
    if day == trading_day(ctx.now):
        lo, hi, _day = trading_window("today", ctx.now)
    elif day == trading_day(ctx.now) - timedelta(days=1):
        lo, hi, _day = trading_window("yesterday", ctx.now)
    else:
        lo, hi = _day_window(day)
    cents, n = ctx.db.query(func.coalesce(func.sum(models.Order.total), 0), func.count(models.Order.id)).filter(
        models.Order.restaurant_id == ctx.rid, models.Order.is_paid.is_(True), models.Order.status != models.OrderStatus.CANCELLED,
        models.Order.created_at >= lo, models.Order.created_at < hi).one()
    return cents / 100.0, int(n)


# ── driver 1: holiday ────────────────────────────────────────────────────────

def _holiday(day: date, weekday: str) -> dict:
    from ai.simulation.signals import demand_signals
    reasons = demand_signals(day).get("reasons") or []
    if reasons:
        return {"key": "holiday", "label": "; ".join(reasons), "found": True, "value": None, "unit": "text",
                "note": f"Holidays change who eats out, so this was not a usual {weekday}."}
    return {"key": "holiday", "label": "Public holiday or event", "found": False, "value": None, "unit": "text",
            "note": "No public holiday or school holiday that day."}


# ── driver 2: a top dish ran out ─────────────────────────────────────────────

def _signed(m: models.StockMovement) -> float:
    """A movement as it changes the shelf: stock in and adjustments add (an adjustment is stored with its sign), stock out takes away."""
    return -m.quantity if m.movement_type == models.StockMovementType.OUT else m.quantity


def _ran_short_at(ctx: OwnerContext, item: models.InventoryItem, day: date, serving: float) -> datetime | None:
    """When on `day` the shelf fell below one serving of this ingredient (Nairobi time), from the stock ledger: the balance at the start of the
    day is the quantity now, less everything recorded since. None if it never did, or if nothing was recorded that day (then the balance is a guess)."""
    lo, hi = _day_window(day)
    moves = ctx.db.query(models.StockMovement).filter(models.StockMovement.inventory_item_id == item.id, models.StockMovement.created_at >= lo
                                                      ).order_by(models.StockMovement.created_at, models.StockMovement.id).all()
    if not any(m.created_at < hi for m in moves):
        return None
    serving -= 1e-6                                                     # floating-point slack: exactly one serving left is not "short"
    level = (item.quantity or 0.0) - sum(_signed(m) for m in moves)
    if level < serving:
        return lo + EAT_OFFSET                                      # it was already short when the day began
    for m in moves:
        if m.created_at >= hi:
            break
        before, level = level, level + _signed(m)
        if before >= serving > level:
            return m.created_at + EAT_OFFSET
    return None


def _stock_out(ctx: OwnerContext, day: date, usual: list[date], busy: float) -> dict:
    """`busy` is the day's sales as a share of a usual day: a quiet day sells less of everything, so what is missed is scaled by it."""
    none = {"key": "stock_out", "label": "A top dish running out", "found": False, "value": None, "unit": "kes"}
    lo_first, _ = _day_window(min(usual))
    _, hi = _day_window(day)
    rows = ctx.db.query(models.Order.created_at, models.OrderItem.menu_item_id, models.OrderItem.quantity, models.OrderItem.unit_price).join(
        models.OrderItem, models.OrderItem.order_id == models.Order.id).filter(
        models.Order.restaurant_id == ctx.rid, models.Order.is_paid.is_(True), models.Order.status != models.OrderStatus.CANCELLED,
        models.Order.created_at >= lo_first, models.Order.created_at < hi).all()
    if not rows:
        return {**none, "note": "No dish sales recorded to check."}
    usual_set = set(usual)
    usual_units: dict[int, int] = defaultdict(int)
    on_day: dict[int, list[datetime]] = defaultdict(list)
    last_order: datetime | None = None
    for created, dish, qty, _price in rows:
        local = created + EAT_OFFSET
        if local.date() == day:
            on_day[dish].append(local)
            last_order = max(last_order, local) if last_order else local
        elif local.date() in usual_set:
            usual_units[dish] += qty
    best = None
    for dish in sorted(usual_units, key=usual_units.get, reverse=True)[:8]:                # the dishes that sell most on a usual day
        for ing, per_serving in ctx.db.query(models.InventoryItem, models.MenuIngredient.raw_quantity_per_serving).join(
                models.MenuIngredient, models.MenuIngredient.inventory_item_id == models.InventoryItem.id).filter(
                models.MenuIngredient.menu_item_id == dish, models.MenuIngredient.is_critical.is_(True), models.InventoryItem.restaurant_id == ctx.rid):
            short_at = _ran_short_at(ctx, ing, day, per_serving or 0.0)
            if short_at is None or any(t > short_at for t in on_day.get(dish, [])):
                continue                                                                   # it kept selling after the shelf was empty: the ledger is not telling the truth
            if last_order is not None and last_order - short_at < WHY.keep_trading:
                continue                                                                   # the restaurant stopped about when the shelf did
            late_value = 0
            for created, d, qty, price in rows:
                local = created + EAT_OFFSET
                if d == dish and local.date() in usual_set and local.time() > short_at.time():
                    late_value += qty * price
            lost = late_value / len(usual) / 100.0 * busy
            if best is None or (lost, -short_at.timestamp()) > (best[2], -best[1].timestamp()):
                best = (dish, short_at, lost, ing.item_name, bool(on_day.get(dish)))
    if best is None:
        return {**none, "note": "No ingredient of a top dish ran short that day."}
    dish_id, short_at, lost, ingredient, sold_any = best
    name = ctx.db.query(models.MenuItem.name).filter(models.MenuItem.id == dish_id, models.MenuItem.restaurant_id == ctx.rid).scalar()
    last_plate = max(on_day[dish_id]) if on_day.get(dish_id) else None
    sold = f"the last {name} sold at {clock_text(last_plate)} and none after" if last_plate else f"no {name} sold that day"
    note = (f"The {ingredient.lower()} ran short at {clock_text(short_at)} (less than one serving left); {sold}, "
            f"while the restaurant went on taking orders until {clock_text(last_order)}.")
    if lost >= 1:
        note += f" On a day this busy that would usually have been about {kes_text(lost)} of {name}."
    return {"key": "stock_out", "label": f"{name} ran out", "found": True, "value": round(lost, 2) if lost >= 1 else None,
            "unit": "kes" if lost >= 1 else "text", "note": note, "dish": name, "ingredient": ingredient}


# ── driver 3: fewer staff ────────────────────────────────────────────────────

def _hours(ctx: OwnerContext, day: date) -> float:
    return float(ctx.db.query(func.coalesce(func.sum(func.coalesce(models.LaborShift.actual_hours, models.LaborShift.scheduled_hours)), 0.0)).filter(
        models.LaborShift.restaurant_id == ctx.rid, models.LaborShift.shift_date == day).scalar() or 0.0)


def _staffing(ctx: OwnerContext, day: date, usual: list[date], weekday: str) -> dict:
    base = {"key": "staffing", "label": "Fewer staff", "found": False, "value": None, "unit": "hours"}
    usual_hours = [h for h in (_hours(ctx, d) for d in usual) if h > 0]
    if not usual_hours:
        return {**base, "note": "No staff shifts recorded to compare."}
    mean = sum(usual_hours) / len(usual_hours)
    that = _hours(ctx, day)
    if that < WHY.staff_share * mean:
        return {**base, "found": True, "value": round(mean - that, 1),
                "note": f"{that:g} staff hours worked, against about {mean:.0f} on a usual {weekday}."}
    return {**base, "note": f"{that:g} staff hours worked, in line with a usual {weekday}."}


# ── driver 4: cancelled sales ────────────────────────────────────────────────

def _cancelled(ctx: OwnerContext, day: date, usual: list[date], weekday: str) -> dict:
    base = {"key": "cancelled_sales", "label": "Cancelled sales", "found": False, "value": None, "unit": "kes"}

    def count_value(d: date) -> tuple[int, float]:
        lo, hi = _day_window(d)
        n, cents = ctx.db.query(func.count(models.Order.id), func.coalesce(func.sum(models.Order.total), 0)).filter(
            models.Order.restaurant_id == ctx.rid, models.Order.status == models.OrderStatus.CANCELLED,
            models.Order.created_at >= lo, models.Order.created_at < hi).one()
        return int(n), cents / 100.0
    n, value = count_value(day)
    usual_counts = [count_value(d) for d in usual]
    mean_n = sum(c[0] for c in usual_counts) / len(usual_counts)
    mean_v = sum(c[1] for c in usual_counts) / len(usual_counts)
    if n >= WHY.min_cancelled and n >= WHY.cancel_multiple * mean_n:
        return {**base, "found": True, "value": round(value, 2),
                "note": f"{n} sales were cancelled, against about {mean_n:.0f} on a usual {weekday}. A reason to look, not a finding about anyone."}
    return {**base, "note": f"{n} sales cancelled, in line with a usual {weekday} (about {mean_n:.0f})."}


# ── the answer ───────────────────────────────────────────────────────────────

def build(ctx: OwnerContext, question: str, *, day: date | None = None) -> dict:
    # The open service day: before 06:00 Nairobi "yesterday" is the day before the service still running.
    today = service_day(ctx.now)
    named = day
    day = named or parse_day(question, today)
    if named is None and re.search(r"\btoday\b", question.lower()):
        day = service_day(ctx.now)
    weekday = day.strftime("%A")
    pretty = day_text(day)
    follow = ["Compare this week with last week", "What should I do to make more money?"]
    sales, orders = _sales(ctx, day)
    if not orders:
        return nothing("why", "why", question, f"No sales are recorded for {pretty}, so there is nothing to explain.", next=follow,
                       day=day.isoformat(), weekday=weekday, drivers=[])
    usual_days = [day - timedelta(days=7 * k) for k in range(1, WHY.usual_days + 1)]
    usual_sales = [s for s, n in (_sales(ctx, d) for d in usual_days) if n]
    if len(usual_sales) < WHY.min_usual:
        return make("why", "why", question, state="learning", reason=f"Only {len(usual_sales)} earlier {weekday}s have sales so far.",
                    headline=f"There are only {len(usual_sales)} earlier {weekday}s recorded, too few to say what a usual {weekday} looks like.",
                    rows=[row("sales", f"Sales on {pretty}", sales, "kes")], next=follow, day=day.isoformat(), weekday=weekday, drivers=[],
                    **{"day_n": len(usual_sales), "of": WHY.min_usual})
    usual = sum(usual_sales) / len(usual_sales)
    gap_pct = (usual - sales) / usual * 100.0 if usual else 0.0
    drivers = [_holiday(day, weekday), _stock_out(ctx, day, usual_days, sales / usual if usual else 1.0), _staffing(ctx, day, usual_days, weekday), _cancelled(ctx, day, usual_days, weekday)]
    found = [d for d in drivers if d["found"]]
    rows = [row("sales", f"Sales on {pretty}", sales, "kes"), row("usual", f"A usual {weekday}", usual, "kes", f"the average of the last {len(usual_sales)} {weekday}s"),
            row("gap_pct", "Below a usual day" if gap_pct >= 0 else "Above a usual day", abs(gap_pct), "pct")]
    if gap_pct > 0:
        head = f"Sales on {pretty} were {kes_text(sales)}, {pct_text(gap_pct)} below a usual {weekday} ({kes_text(usual)})."
    else:
        head = f"Sales on {pretty} were {kes_text(sales)}, {pct_text(abs(gap_pct))} above a usual {weekday} ({kes_text(usual)}); they were not down."
    if found:
        head += " What the records show: " + "; ".join(_phrase(d) for d in found) + "."
    elif gap_pct > 0:
        head += " Nothing in the records explains the gap; it may simply be a slower day."
    state = ctx.order_state()
    assumptions = [
        assumption(f"A usual {weekday} is the average of the {len(usual_sales)} before it that had sales."),
        assumption(f"An ingredient counts as having run out when the stock ledger shows less than one serving left, no plate of the dish sold after that, "
                   f"and the restaurant kept taking orders for at least {int(WHY.keep_trading.total_seconds() // 60)} minutes more."),
        assumption("These are what the records show, not proof of a cause, and they do not add up to the gap."),
    ]
    return make("why", "why", question, state=state["state"], as_of=state.get("as_of"), headline=head, rows=rows, assumptions=assumptions,
                next=follow, day=day.isoformat(), weekday=weekday, drivers=drivers)


def _phrase(d: dict) -> str:
    if d["key"] == "holiday":
        return d["label"].replace("Public holiday: ", "it was a public holiday (") + (")" if d["label"].startswith("Public holiday: ") else "")
    if d["key"] == "stock_out":
        return f"{d['dish']} ran out early" + (f" (about {kes_text(d['value'])} of sales missed)" if d["value"] else "")
    if d["key"] == "staffing":
        return f"{d['value']:g} fewer staff hours than usual"
    return f"cancelled sales were {kes_text(d['value'])}"
