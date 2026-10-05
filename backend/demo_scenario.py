"""Small, deterministic demonstration. No database access or generated transactions.

Money is integer KES here (unlike operational cents APIs). All surfaces consume
this same scenario; projections and opportunities are never realised savings.
Every figure shown to the owner is derived from the values below, never typed
into copy by hand, so the pages, the OS answers and the PDF report always agree.
"""
import math
from datetime import date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo
from statistics import mean, pstdev

VERSION = "owner-demo-v2"
NOTICE = "Illustrative demo · calculated from a compact sample scenario, not actual restaurant results."
AREAS = {
    "revenue": "Revenue", "orders": "Orders", "kitchen": "Kitchen", "stock": "Stock",
    "bookings": "Bookings", "team": "Team", "menu": "Menu & pricing", "finance": "Finance",
    "expenses": "Expenses", "suppliers": "Suppliers", "purchasing": "Purchasing",
    "cash-reconciliation": "Cash reconciliation", "pos": "Point of sale", "marketing": "Marketing",
    "risk": "Fraud and risk", "notifications": "Notifications", "intelligence": "Business intelligence",
    "data-trust": "Data trust", "audit": "Audit trail", "settings": "Restaurant settings",
}
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# One recipe per dish (quantity used per portion). Stock is derived from these,
# so every ingredient on the Stock page is traceable to a dish on the Menu page.
RECIPES = {
    "Beef pilau": {"Beef": 0.125, "Rice": 0.15, "Onions": 0.05, "Cooking oil": 0.02, "Pilau masala": 0.005},
    "Chicken rice": {"Chicken": 0.2, "Rice": 0.15, "Mixed vegetables": 0.05, "Cooking oil": 0.02},
    "Grilled fish": {"Tilapia": 0.35, "Mixed vegetables": 0.08, "Lemons": 0.5, "Cooking oil": 0.02},
    "Vegetable bowl": {"Mixed vegetables": 0.25, "Rice": 0.1, "Cooking oil": 0.015},
    "Fresh juice": {"Fresh fruit": 0.25, "Sugar": 0.02},
    "Chai": {"Milk": 0.1, "Tea leaves": 0.004, "Sugar": 0.01},
}
UNITS = {"Beef": "kg", "Chicken": "kg", "Tilapia": "kg", "Rice": "kg", "Mixed vegetables": "kg", "Onions": "kg",
         "Cooking oil": "L", "Pilau masala": "kg", "Lemons": "pcs", "Fresh fruit": "kg", "Milk": "L",
         "Tea leaves": "kg", "Sugar": "kg"}
ON_HAND = {"Beef": 6, "Chicken": 12, "Tilapia": 10.5, "Rice": 40, "Mixed vegetables": 14.5, "Onions": 9,
           "Cooking oil": 18, "Pilau masala": 1.2, "Lemons": 40, "Fresh fruit": 16, "Milk": 14,
           "Tea leaves": 1.5, "Sugar": 10}
SUPPLIER_OF = {"Beef": "Meat & fish partner", "Chicken": "Meat & fish partner", "Tilapia": "Meat & fish partner",
               "Mixed vegetables": "Produce partner", "Onions": "Produce partner", "Lemons": "Produce partner",
               "Fresh fruit": "Produce partner", "Rice": "Dry goods & dairy partner",
               "Cooking oil": "Dry goods & dairy partner", "Pilau masala": "Dry goods & dairy partner",
               "Sugar": "Dry goods & dairy partner", "Tea leaves": "Dry goods & dairy partner",
               "Milk": "Dry goods & dairy partner"}
NEAR_EXPIRY = {"Mixed vegetables": 8}   # kg that must be used within 48 hours
LOW_COVER_DAYS = 2.0                     # order when stock covers two days or less
SCHEDULED_TODAY = 8                      # people scheduled today
COVERS_TODAY = 42                        # guests expected tonight
SOON_DAYS = 3.0                          # "running out soon" means within this many days of expected sales
LABOR_KES = 10500
OTHER_COSTS_KES = 6500
UNMATCHED_KES = 1200
# Today's service snapshot. Home, the area pages and the OS answers all read these.
ORDERS_TODAY = 70
OPEN_ORDERS = 6                          # tickets still being prepared
DELAYED_ORDERS = 2
AVG_PREP_MIN = 14
BOTTLENECK = "Grill station"
GRILL_MIN, COLD_MIN = 22, 8              # slowest and fastest station prep time
WAITLIST = 4
NO_SHOW_PCT = 6
ON_SHIFT = 6
OVERTIME_HOURS = 3                       # avoidable overtime hours today
NEXT_RESERVATION_MIN = 45
DINE_IN_TODAY, TAKEAWAY_TODAY = 45, 18   # orders by channel today; delivery is the rest (see _channels)
LUNCH_PEOPLE, DINNER_PEOPLE = 6, 4       # people covering each service today
RETURNING_GUESTS = 28                    # of today's guests; the rest are new
# Tonight's bookings. Their covers add up to COVERS_TODAY (a test holds that).
BOOKING_SLOTS = [("18:00", 12, "Confirmed"), ("19:00", 18, "Confirmed"), ("20:00", 12, "Awaiting confirmation")]
# Open purchase orders: number, supplier, amount in KES, state.
PURCHASE_ORDERS = [("PO-D1", "Dry goods & dairy partner", 12000, "Waiting for your approval"),
                   ("PO-D2", "Meat & fish partner", 6000, "Delivery overdue")]


def today():
    return datetime.now(ZoneInfo("Africa/Nairobi")).date()


def money(v):
    return f"KES {round(v):,}"


def qty(v):
    return f"{v:g}"


@lru_cache(maxsize=2)
def scenario(day: date):
    # Eight repetitions of a weekly sales pattern, with a modest upward trend.
    # 56 aggregate rows, six dishes, three controllable opportunities. Zero DB rows.
    menu = [("Beef pilau", 650, 270, 24), ("Chicken rice", 750, 320, 20),
            ("Grilled fish", 950, 420, 12), ("Vegetable bowl", 450, 140, 18),
            ("Fresh juice", 250, 70, 30), ("Chai", 100, 25, 36)]
    base = sum(price * n for _, price, _, n in menu)
    pattern = [82, 88, 94, 100, 118, 135, 108]
    history = []
    for i in range(56):
        d = day - timedelta(days=55 - i)
        revenue = base * pattern[d.weekday()] * (94 + i // 7) // 10000
        history.append({"date": d.isoformat(), "revenue": revenue, "orders": max(1, revenue // 900)})
    # Today's menu is the exact source for today's sales and cost totals.
    history[-1] = {"date": day.isoformat(), "revenue": base, "orders": ORDERS_TODAY}
    spread = round(pstdev([r["revenue"] for r in history]))
    overall = mean(r["revenue"] for r in history)
    forecast = []
    for offset in range(1, 8):
        d = day + timedelta(days=offset)
        values = [r["revenue"] for r in history if date.fromisoformat(r["date"]).weekday() == d.weekday()]
        estimate = round(mean(values))
        row = {"date": d.isoformat(), "day": DAY_NAMES[d.weekday()], "revenue": estimate,
               "low": max(0, estimate - spread), "high": estimate + spread}
        gap = round((estimate - overall) / overall * 100)
        name = DAY_NAMES[d.weekday()]
        if gap <= -8:
            feel = (f"{name}s are one of your quieter days. Over the last {len(values)} weeks they averaged "
                    f"{money(estimate)}, about {abs(gap)}% below a typical day ({money(overall)}). "
                    "Prepare a little less and keep staffing lean.")
        elif gap >= 8:
            feel = (f"{name}s are one of your busier days. Over the last {len(values)} weeks they averaged "
                    f"{money(estimate)}, about {gap}% above a typical day ({money(overall)}). "
                    "Prepare more, and make sure the kitchen and floor are fully covered.")
        else:
            feel = (f"{name}s are close to a typical day. Over the last {len(values)} weeks they averaged "
                    f"{money(estimate)}, in line with your usual {money(overall)}.")
        row["why"] = feel + f" A normal {name} can land anywhere between {money(row['low'])} and {money(row['high'])}."
        forecast.append(row)
    opportunities = [
        {"id": "waste", "area": "stock", "title": "Use vegetables before expiry", "quantity": 8, "unit_value": 180,
         "why": "8 kg can be used before expiry instead of discarded.", "action": "Prioritise the vegetable bowl and check the next delivery."},
        {"id": "margin", "area": "menu", "title": "Test the pilau price", "quantity": 24, "unit_value": 30,
         "why": "24 daily portions × KES 30 price change; assumes unchanged demand.", "action": "Compare contribution before approving a price change."},
        {"id": "labor", "area": "team", "title": "Shift coverage into the dinner rush", "quantity": OVERTIME_HOURS, "unit_value": 250,
         "why": f"{OVERTIME_HOURS} avoidable overtime hours × KES 250 per hour.", "action": "Move existing coverage into the busy service window."},
    ]
    for item in opportunities:
        item["value"] = item["quantity"] * item["unit_value"]
    # Stock: what today's menu uses, against what is on the shelf.
    usage, used_in = {}, {}
    for dish, _price, _cost, portions in menu:
        for ing, per in RECIPES[dish].items():
            usage[ing] = usage.get(ing, 0) + per * portions
            used_in.setdefault(ing, []).append(dish)
    # What each coming day asks of the restaurant. The system learns how sales differ by weekday, and
    # assumes each day sells the same mix of dishes as today, scaled to that day's expected sales.
    ratios = [r["revenue"] / base for r in forecast]
    plates_today = sum(n for *_, n in menu)
    for row, ratio in zip(forecast, ratios):
        row["plates"] = round(plates_today * ratio)
        row["people"] = math.ceil(SCHEDULED_TODAY * ratio)
        row["covers"] = round(COVERS_TODAY * ratio)
    stock = []
    for ing, unit in UNITS.items():
        daily = round(usage[ing], 2)
        cover = round(ON_HAND[ing] / daily, 1)
        uses = [usage[ing] * x for x in ratios]
        remaining, runway, out_index = ON_HAND[ing], None, None
        for i, use in enumerate(uses):
            if remaining >= use:
                remaining -= use
            else:
                runway, out_index = round(i + remaining / use, 1), i
                break
        if runway is None:
            runway = round(len(uses) + remaining / (sum(uses) / len(uses)), 1)
        need = sum(uses)
        # Suppliers need about a day, so order the day before it would be needed.
        order_by = None
        if out_index is not None:
            order_by = "Today" if out_index < 2 else forecast[out_index - 2]["day"]
        stock.append({"name": ing, "unit": unit, "on_hand": ON_HAND[ing], "daily_use": daily, "cover_days": cover,
                      "used_in": used_in[ing], "supplier": SUPPLIER_OF[ing], "low": cover <= LOW_COVER_DAYS,
                      "near_expiry": NEAR_EXPIRY.get(ing, 0), "runway_days": runway,
                      "runs_out_day": forecast[out_index]["day"] if out_index is not None else None,
                      "order_by": order_by, "need_7d": round(need, 1),
                      "order_qty": max(0, math.ceil(need - ON_HAND[ing]))})
    return {"history": history, "menu": menu, "forecast": forecast, "opportunities": opportunities,
            "food_cost": sum(cost * n for _, _, cost, n in menu), "stock": stock, "overall": round(overall)}


def growth(s):
    """Average daily sales, last 7 days against the 7 days before."""
    last = mean(r["revenue"] for r in s["history"][-7:])
    before = mean(r["revenue"] for r in s["history"][-14:-7])
    return last, before, round((last - before) / before * 100, 1)


def weekday_pattern(s):
    out = []
    for w in range(7):
        vals = [r["revenue"] for r in s["history"] if date.fromisoformat(r["date"]).weekday() == w]
        out.append({"day": DAY_NAMES[w][:3], "revenue": round(mean(vals))})
    return out


def roi(day=None):
    s = scenario(day or today())
    return {"opportunities": s["opportunities"], "potential_daily": sum(x["value"] for x in s["opportunities"]),
            "label": "Illustrative daily opportunity", "realised": 0,
            "assumption": "Independent scenario opportunities; not guaranteed or realised savings. No subscription ROI percentage is claimed without an actual fee."}


def _dish_rows(s):
    return [{"name": n, "price": p, "cost": c, "units": q, "sales": p * q, "contribution": (p - c) * q,
             "margin_pct": round((p - c) / p * 100)} for n, p, c, q in s["menu"]]


def _channels(orders):
    """The one place orders are split by channel, in today's proportions, for any period."""
    dine = orders * DINE_IN_TODAY // ORDERS_TODAY
    take = orders * TAKEAWAY_TODAY // ORDERS_TODAY
    return [{"label": "Dine-in", "value": dine}, {"label": "Takeaway", "value": take},
            {"label": "Delivery", "value": orders - dine - take}]


def _decision(idea, why, next_step, expected=None):
    return {"idea": idea, "why": why, "next_step": next_step, "expected": expected}


def _alert(id_, title, why, what_to_do, level="watch", impact=None, repeat_of=None):
    """`repeat_of` names the opportunity or alert that already says this, so Home shows it once."""
    alert = {"id": id_, "title": title, "why": why, "what_to_do": what_to_do, "level": level, "impact": impact}
    if repeat_of:
        alert["repeat_of"] = repeat_of
    return alert


def report(period, day=None):
    day = day or today()
    s = scenario(day)
    start = {"daily": day, "weekly": day - timedelta(days=day.weekday()),
             "monthly": day.replace(day=1), "yearly": day.replace(month=1, day=1)}[period]
    rows = [r for r in s["history"] if r["date"] >= start.isoformat()]
    revenue, orders = sum(r["revenue"] for r in rows), sum(r["orders"] for r in rows)
    label = {"daily": "today", "weekly": "this week so far", "monthly": "this month so far", "yearly": "this year so far"}[period]
    text = f"Illustrative {period} report: KES {revenue:,} revenue across {orders} orders. "
    text += f"Coverage: {rows[0]['date']} to {day.isoformat()} ({len(rows)} sample days). "
    text += "Prioritise expiry waste, menu contribution and overtime. Forecasts are estimates; savings have not been realised."

    # Compare with the same span one step back (same weekday last week, same days last week, ...).
    shift = {"daily": 7, "weekly": 7, "monthly": None, "yearly": None}[period]
    comparison = None
    if period == "monthly":
        prev_first = (start - timedelta(days=1)).replace(day=1)
        prev_start, span = prev_first, len(rows)
    elif shift:
        prev_start, span = start - timedelta(days=shift), len(rows)
    else:
        prev_start = None
    if prev_start:
        prev_days = {(prev_start + timedelta(days=i)).isoformat() for i in range(span)}
        prev_rows = [r for r in s["history"] if r["date"] in prev_days]
        if len(prev_rows) == span:
            prev_revenue = sum(r["revenue"] for r in prev_rows)
            comparison = {"label": {"daily": f"last {DAY_NAMES[day.weekday()]}", "weekly": "the same days last week",
                                    "monthly": "the same days last month"}[period],
                          "previous_revenue": prev_revenue,
                          "change_pct": round((revenue - prev_revenue) / prev_revenue * 100, 1)}
    # Chart series: a single day is shown in the context of the last 7 days.
    chart_rows = s["history"][-7:] if period == "daily" else rows
    if period == "yearly":
        weeks, bucket = [], []
        for r in rows:
            bucket.append(r)
            if len(bucket) == 7:
                weeks.append({"date": bucket[0]["date"], "day": "wk", "revenue": sum(b["revenue"] for b in bucket),
                              "orders": sum(b["orders"] for b in bucket)})
                bucket = []
        if bucket:
            weeks.append({"date": bucket[0]["date"], "day": "wk", "revenue": sum(b["revenue"] for b in bucket),
                          "orders": sum(b["orders"] for b in bucket)})
        series = weeks
    else:
        series = [{"date": r["date"], "day": DAY_NAMES[date.fromisoformat(r["date"]).weekday()][:3],
                   "revenue": r["revenue"], "orders": r["orders"]} for r in chart_rows]
    # A single day is judged against the last 7 days; longer periods against themselves.
    span = s["history"][-7:] if period == "daily" else rows
    scope = "in the last 7 days" if period == "daily" else "in this period"
    best = max(span, key=lambda r: r["revenue"])
    quiet = min(span, key=lambda r: r["revenue"])
    dishes = _dish_rows(s)
    total_sales = sum(d["sales"] for d in dishes)
    today_row = s["history"][-1]
    margin = today_row["revenue"] - s["food_cost"]
    last7, before7, g = growth(s)

    if period == "daily":
        headline = (f"Today ({DAY_NAMES[day.weekday()]}) the restaurant took {money(revenue)} from {orders} orders, "
                    f"an average of {money(revenue // orders)} per order.")
    else:
        headline = (f"{label.capitalize()} the restaurant took {money(revenue)} from {orders} orders over {len(rows)} "
                    f"sample days, an average of {money(revenue // len(rows))} per day.")
    if comparison:
        word = "up" if comparison["change_pct"] >= 0 else "down"
        headline += f" That is {word} {abs(comparison['change_pct'])}% on {comparison['label']}."
    beef_out = next(x["runs_out_day"] for x in s["stock"] if x["name"] == "Beef")
    story = [
        {"title": "Sales", "text": f"Your best day {scope} was {DAY_NAMES[date.fromisoformat(best['date']).weekday()]} "
                                   f"{best['date'][5:]} at {money(best['revenue'])}; the quietest was "
                                   f"{DAY_NAMES[date.fromisoformat(quiet['date']).weekday()]} {quiet['date'][5:]} at {money(quiet['revenue'])}. "
                                   f"Over the last week you averaged {money(last7)} a day, {abs(g)}% "
                                   f"{'more' if g >= 0 else 'less'} than the week before."},
        {"title": "Menu and money", "text": f"Today's dishes brought in {money(total_sales)} and cost {money(s['food_cost'])} to make, "
                                            f"leaving {money(margin)} to pay for staff and running costs. "
                                            f"{max(dishes, key=lambda d: d['contribution'])['name']} earns the most for the business "
                                            f"({money(max(d['contribution'] for d in dishes))} today)."},
        {"title": "Stock and waste", "text": f"With the sales we expect, beef runs out on {beef_out} and the meat delivery is a day late, so order today. "
                                             f"{NEAR_EXPIRY['Mixed vegetables']} kg of vegetables need to be used within 2 days so they are not thrown away."},
        {"title": "Team", "text": f"Labour is about {round(LABOR_KES / today_row['revenue'] * 100, 1)}% of today's sales. "
                                   "3 overtime hours could be moved into the dinner rush instead of paid on top."},
        {"title": "Cash and safety", "text": f"{money(UNMATCHED_KES)} of payments has not been matched to a sale yet. "
                                              "That is not proof of loss; check the payment reference first."},
    ]
    decisions = [_decision(x["title"], x["why"], x["action"], f"{money(x['value'])} potential / day") for x in s["opportunities"]]
    return {"period": period, "range": f"{rows[0]['date']} – {day.isoformat()}", "revenue": revenue, "orders": orders,
            "top_items": [{"name": n, "qty": q, "sales_kes": p * q} for n, p, c, q in s["menu"]] if period == "daily" else [],
            "report_text": text, "llm_used": False, "coverage_days": len(rows), "notice": NOTICE,
            "label": label, "headline": headline, "comparison": comparison, "series": series,
            "weekday_pattern": weekday_pattern(s), "channels": _channels(ORDERS_TODAY), "dishes": dishes,
            "best_day": best, "quiet_day": quiet, "story": story, "decisions": decisions,
            "kpis": [{"label": "Sales", "value": money(revenue)}, {"label": "Orders", "value": f"{orders:,}"},
                     {"label": "Average order", "value": money(revenue // orders)},
                     ({"label": "Kept after ingredients", "value": money(margin)} if period == "daily"
                      else {"label": "Best day", "value": money(best["revenue"])})],
            "money_today": {"sales": today_row["revenue"], "food_cost": s["food_cost"], "contribution": margin,
                            "labor": LABOR_KES, "other": OTHER_COSTS_KES,
                            "surplus": margin - LABOR_KES - OTHER_COSTS_KES},
            "note": ("Dish and cost detail is for today's sample menu." if period != "daily" else "")
                    + (" Only 56 sample days exist, so 'this year' shows those days rather than a full year." if period == "yearly" else "")}


PERIOD_LABELS = {"1h": "The last hour", "today": "Today", "7d": "The last 7 days", "30d": "The last 30 days"}


@lru_cache(maxsize=2)
def attention_items(day: date):
    """Everything that needs the owner, read from the area pages so Home cannot disagree with them.

    `attention`: urgent alerts first, then the opportunity cards (each carries its KES sum).
    `watching`: the lower-priority alerts, kept visible but compact."""
    s = scenario(day)
    alerts = []
    for key in AREAS:
        if key == "notifications":      # built from this list, so it is not a source
            continue
        for a in area(key, day)["attention"]:
            if a.get("repeat_of"):      # another card already says this; Home shows it once
                continue
            alerts.append({"id": a["id"], "domain": AREAS[key], "title": a["title"], "why": a["why"],
                           "what_to_do": a["what_to_do"], "impact": a["impact"] or "", "status": "open",
                           "level": a["level"], "link": key})
    urgent = [a for a in alerts if a["level"] == "urgent"]
    opportunities = [{"id": x["id"], "domain": AREAS[x["area"]], "title": x["title"], "why": x["why"],
                      "what_to_do": x["action"], "impact": f"KES {x['value']:,} potential / day", "status": "open",
                      "level": "opportunity", "link": x["area"]} for x in s["opportunities"]]
    return {"attention": urgent + opportunities, "watching": [a for a in alerts if a["level"] != "urgent"]}


def home(period="today", day=None):
    day = day or today()
    s = scenario(day)
    # The one-hour window is an explicit sample slice, never passed off as live.
    count = {"today": 1, "7d": 7, "30d": 30, "1h": 1}[period]
    rows = s["history"][-count:]
    revenue, orders = sum(r["revenue"] for r in rows), sum(r["orders"] for r in rows)
    if period == "1h":
        revenue, orders = revenue // 8, max(1, orders // 8)
    note = ("One eighth of today's sample sales, not a live hour." if period == "1h"
            else "Revenue and orders follow the period. Kitchen, stock, bookings and staff always show right now.")
    low = [x for x in s["stock"] if x["low"]]
    soon = sorted((x for x in s["stock"] if x["runway_days"] <= SOON_DAYS), key=lambda z: z["runway_days"])
    first_low = low[0] if low else None
    items = attention_items(day)
    forecast = s["forecast"]
    busy = max(forecast, key=lambda r: r["revenue"])
    quiet = min(forecast, key=lambda r: r["revenue"])
    today_row = s["history"][-1]
    money_today = report("daily", day)["money_today"]
    to_order = [x for x in s["stock"] if x["order_qty"] > 0]
    pulse = [
        {"domain": "Forecast", "headline": f"KES {sum(r['revenue'] for r in forecast):,} next 7 days", "detail": "Calculated from 56 sample daily summaries; inspect the range in Revenue.", "link": "revenue"},
        {"domain": "Coming days", "headline": f"{busy['day']} looks busiest, {quiet['day']} quietest",
         "detail": f"About {money(busy['revenue'])} expected on {busy['day']} and {money(quiet['revenue'])} on {quiet['day']}.", "link": "revenue"},
        {"domain": "Stock", "headline": f"{len(soon)} ingredients run out within {SOON_DAYS:g} days",
         "detail": f"{len(to_order)} ingredients are on the suggested order list for the week.", "link": "purchasing"},
        {"domain": "Costs today", "headline": f"Ingredients {round(s['food_cost'] / today_row['revenue'] * 100, 1)}% and staff {round(LABOR_KES / today_row['revenue'] * 100, 1)}% of sales",
         "detail": f"{money(money_today['surplus'])} is left after ingredients, staff and running costs.", "link": "finance"},
        {"domain": "Cash control", "headline": f"KES {UNMATCHED_KES:,} settlement exception", "detail": "Investigate an unmatched payment; this is not proven loss or theft.", "link": "cash-reconciliation"},
    ]
    dine_in, takeaway, delivery = (c["value"] for c in _channels(orders))
    return {"restaurant_name": "Demo Restaurant", "greeting_date": day.isoformat(), "period": period,
      "period_label": PERIOD_LABELS[period], "period_note": note,
      "unavailable_metrics": [], "data_provenance": {"notice": NOTICE, "latest_order_at": None},
      "revenue": {"revenue": revenue, "orders": orders, "avg_order": revenue/orders, "pace_projection": 0},
      "orders": {"revenue": revenue, "orders": orders, "delayed": DELAYED_ORDERS, "active_now": OPEN_ORDERS, "split": {"dine_in": dine_in, "takeaway": takeaway, "delivery": delivery}},
      "kitchen": {"avg_prep_min": AVG_PREP_MIN, "delay_risk": DELAYED_ORDERS, "bottleneck": BOTTLENECK},
      "stock": {"recorded_items": len(s["stock"]), "low_stock": [{"name": x["name"], "qty": x["on_hand"], "unit": x["unit"], "runs_out_day": x["runs_out_day"]} for x in low],
                "expiring_48h": [f"{k} · {v} kg" for k, v in NEAR_EXPIRY.items()],
                "soon_count": len(soon),
                "first_low_order": ({"name": first_low["name"], "order_by": first_low["order_by"], "order_qty": first_low["order_qty"], "unit": first_low["unit"]} if first_low else None)},
      "bookings": {"covers_today": COVERS_TODAY, "next_reservation_min": NEXT_RESERVATION_MIN, "waitlist": WAITLIST, "no_show_pct": NO_SHOW_PCT},
      "staff": {"scheduled": SCHEDULED_TODAY, "on_shift": ON_SHIFT, "overtime_risk": OVERTIME_HOURS, "labor_cost_pct": round(LABOR_KES/today_row['revenue']*100,1)},
      "attention": [dict(x) for x in items["attention"]],
      "watching": [dict(x) for x in items["watching"]],
      "pulse": pulse,
      "money_today": money_today,
      "week_ahead": [{"date": r["date"], "day": r["day"], "revenue": r["revenue"], "low": r["low"], "high": r["high"],
                      "plates": r["plates"], "people": r["people"], "covers": r["covers"]} for r in forecast],
      "source_status": {k: {"state": "available", "recommendations": 1} for k in AREAS},
      "performance": {"revenue_trend": s['history'][-7:]}, "roi": roi(day)}


def _stock_area(s):
    rows = []
    for x in s["stock"]:
        lasts = f"{x['runway_days']:g} days (runs out {x['runs_out_day']})" if x["runs_out_day"] else "More than 7 days"
        order = f"{qty(x['order_qty'])} {x['unit']}" if x["order_qty"] > 0 else "Nothing needed"
        rows.append([x["name"], f"{qty(x['on_hand'])} {x['unit']}", f"{qty(x['daily_use'])} {x['unit']}",
                     lasts, order, ", ".join(x["used_in"])])
    return rows


def _order_list(s):
    """Ingredients to order, grouped by supplier, with the day each order is needed by."""
    days = [r["day"] for r in s["forecast"]]
    groups = {}
    for x in sorted((x for x in s["stock"] if x["order_qty"] > 0), key=lambda z: z["runway_days"]):
        rank = -1 if x["order_by"] == "Today" else days.index(x["order_by"])
        g = groups.setdefault(x["supplier"], {"items": [], "rank": rank, "by": x["order_by"]})
        g["items"].append(f"{x['name']} {qty(x['order_qty'])} {x['unit']}")
        if rank < g["rank"]:
            g["rank"], g["by"] = rank, x["order_by"]
    return [[sup, ", ".join(g["items"]), g["by"]] for sup, g in sorted(groups.items(), key=lambda kv: kv[1]["rank"])]


def area(key, day=None):
    day = day or today()
    s = scenario(day)
    revenue = s['history'][-1]['revenue']
    margin = revenue - s['food_cost']
    surplus = margin - LABOR_KES - OTHER_COSTS_KES
    last7, before7, g = growth(s)
    dishes = _dish_rows(s)
    top = max(dishes, key=lambda d: d["contribution"])
    forecast = s["forecast"]
    quiet = min(forecast, key=lambda r: r["revenue"])
    busy = max(forecast, key=lambda r: r["revenue"])
    low = [x for x in s["stock"] if x["low"]]
    beef = next(x for x in s["stock"] if x["name"] == "Beef")
    veg = next(x for x in s["stock"] if x["name"] == "Mixed vegetables")
    veg_two_days = round(veg["daily_use"] * 2, 1)
    pilau = dishes[0]
    rice = next(x for x in s["stock"] if x["name"] == "Rice")
    labor_pct = round(LABOR_KES / revenue * 100, 1)
    food_pct = round(s['food_cost'] / revenue * 100, 1)
    opps = {o["id"]: o for o in s["opportunities"]}
    # What the coming days ask of stock, kitchen and team, learned from expected sales and recipes.
    order_days = [r["day"] for r in forecast]
    busy_i = order_days.index(busy["day"])
    soon = sorted((x for x in s["stock"] if x["runway_days"] <= SOON_DAYS), key=lambda z: z["runway_days"])
    others_soon = [x for x in soon if x["name"] != "Beef"]
    plates_today = sum(d["units"] for d in dishes)
    order_list = _order_list(s)
    to_order_n = sum(1 for x in s['stock'] if x['order_qty'] > 0)
    busy_row = forecast[busy_i]
    late_time, late_covers, _late_state = next(b for b in BOOKING_SLOTS if b[2] != "Confirmed")
    po_first, po_second = PURCHASE_ORDERS
    channels = _channels(ORDERS_TODAY)
    new_guests = ORDERS_TODAY - RETURNING_GUESTS
    before_rush = (f", before {busy['day']}, your busiest day"
                   if beef["runs_out_day"] and order_days.index(beef["runs_out_day"]) < busy_i else "")

    def day_table(title, note, columns, make_row):
        return dict(title=title, note=note, columns=columns, rows=[make_row(r) for r in forecast])

    # Each spec: subtitle, headline, how_to_read, metrics, columns, rows, table_title, table_note, action,
    # attention (what needs attention here), decisions (ideas and why), charts.
    specs = {
      "revenue": dict(
        subtitle="How much money the restaurant is bringing in, and what to expect next.",
        headline=f"You took {money(revenue)} today from {ORDERS_TODAY} orders. Over the last week you averaged {money(last7)} a day, {abs(g)}% {'more' if g >= 0 else 'less'} than the week before.",
        how_to_read="The line shows the last 14 days and the next 7. The shaded band is how far a normal day can move away from what we expect. Tap any coming day to see why we expect that amount.",
        metrics=[('Revenue today', money(revenue)), ('Orders', ORDERS_TODAY), ('Average order', money(revenue // ORDERS_TODAY))],
        columns=['Day', 'Revenue', 'Orders'], rows=[[f"{DAY_NAMES[date.fromisoformat(r['date']).weekday()][:3]} {r['date'][5:]}", money(r['revenue']), r['orders']] for r in s['history'][-7:]],
        table_title="The last 7 days", table_note="Each row is one trading day: what was taken and how many orders it came from.",
        action="Use the expected range to plan stock and staffing, then compare actual sales.",
        attention=[_alert("quiet-day", f"{quiet['day']} looks quiet", f"We expect about {money(quiet['revenue'])} on {quiet['day']}, the lowest of the coming week.", "Prepare a little less and keep staffing lean that day.", "watch")],
        decisions=[_decision(f"Prepare for a busy {busy['day']}", f"{busy['day']} is expected to bring about {money(busy['revenue'])}, your strongest day this week.", "Order stock a day ahead and make sure the floor and kitchen are fully covered.", f"Protects about {money(busy['revenue'])} of sales"),
                   _decision(f"Keep {quiet['day']} lean", f"{quiet['day']}s average {money(quiet['revenue'])}, well below a typical day.", "Cut prep for slow sellers and avoid overtime that day.", "Less waste and lower labour cost")]),
      "orders": dict(
        subtitle="The orders coming in, and whether service is keeping up.",
        headline=f"{ORDERS_TODAY} orders are complete, {OPEN_ORDERS} are being prepared and {DELAYED_ORDERS} are running late.",
        how_to_read="Open orders are still moving through the kitchen. A late order is one that has taken longer than it should; those are the ones to look at first.",
        metrics=[('Completed', ORDERS_TODAY), ('Open', OPEN_ORDERS), ('Delayed', DELAYED_ORDERS)], columns=['Ticket', 'Channel', 'State'],
        rows=[['D-101', 'Dine-in', 'Preparing'], ['D-102', 'Takeaway', 'Ready'], ['D-103', 'Delivery', 'Delayed']],
        table_title="Orders that need a look", table_note="A short list of orders in progress right now.",
        action="Prioritise delayed tickets and review service time.",
        attention=[_alert("late-orders", f"{DELAYED_ORDERS} orders are running late", "One delivery order (D-103) has waited longer than usual.", "Check the grill queue and let the customer know.", "urgent")],
        decisions=[_decision("Clear the late delivery first", "Delivery customers cannot see the kitchen, so delays turn into complaints quickly.", "Send the late delivery next and call the customer.", "Protects the customer relationship")]),
      "kitchen": dict(
        subtitle="What is being prepared, and where the kitchen is slowing down.",
        headline=f"Average preparation is {AVG_PREP_MIN} minutes. The grill is the slowest station at {GRILL_MIN} minutes while the cold station is waiting at {COLD_MIN}.",
        how_to_read="Prep time is how long a dish takes from order to plate. When one station is far slower than the others, orders queue behind it.",
        metrics=[('Average prep', f'{AVG_PREP_MIN} min'), ('Open tickets', OPEN_ORDERS), ('Delayed', DELAYED_ORDERS)], columns=['Station', 'Prep time', 'What to do'],
        rows=[['Grill', f'{GRILL_MIN} min', 'Rebalance queue'], ['Cold station', f'{COLD_MIN} min', 'Support plating']],
        table_title="Stations right now", table_note="Slowest first. The idea is to move a helper to the slowest station.",
        action="Move plating support to the grill before the dinner rush.",
        attention=[_alert("grill", "The grill is the bottleneck", f"Grill dishes (grilled fish, beef) take {GRILL_MIN} minutes while the cold station finishes in {COLD_MIN}.", "Move plating support to the grill before the dinner rush.", "urgent")],
        decisions=[_decision("Share the load before dinner", f"{DELAYED_ORDERS} orders are already late and dinner is your busiest time.", "Ask the cold station to help plate grill orders.", "Fewer late orders"),
                   _decision(f"Plan extra hands for {busy['day']}", f"We expect about {busy_row['plates']} plates on {busy['day']}, {round((busy_row['plates'] / plates_today - 1) * 100)}% more than today, and the grill already takes {GRILL_MIN} minutes.", "Put one extra person on the grill and pre-prepare the sauces the day before.", "Fewer late orders on your busiest day")],
        extra_tables=[day_table("Plates we expect to prepare", "Worked out from the sales we expect each day. We assume the same mix of dishes as today.", ['Day', 'Expected sales', 'Plates', 'Compared with today'], lambda r: [r['day'], money(r['revenue']), r['plates'], f"{round((r['plates'] / plates_today - 1) * 100):+d}%"])]),
      "stock": dict(
        subtitle="What is on the shelf, how long it will last, and what to order.",
        headline=f"You track {len(s['stock'])} ingredients, all used by the dishes on your menu. With the sales we expect, beef runs out on {beef['runs_out_day']}, and {len(others_soon)} more ingredients run out within {SOON_DAYS:g} days unless you restock.",
        how_to_read="We work this out from your recipes and how much you expect to sell each day: a busy Saturday uses more than a quiet Monday. 'Lasts' is how long the stock will last with those expected sales if nothing new arrives. As your sales change, these estimates change too. We assume each day sells the same mix of dishes as today.",
        metrics=[('Ingredients tracked', len(s['stock'])), ('Order today', len(low)), (f'Run out within {SOON_DAYS:g} days', len(soon))],
        columns=['Ingredient', 'On hand', 'Used per day (today)', 'Lasts (with expected sales)', 'Order about', 'Used in'], rows=_stock_area(s),
        table_title="Everything on the shelf", table_note="'Order about' is what would cover the next 7 days of expected sales.",
        action="Use expiry stock first and order the ingredients that run out first.",
        attention=[_alert("beef-low", f"Beef runs out on {beef['runs_out_day']}", f"You have {qty(beef['on_hand'])} kg. With the sales we expect it lasts about {beef['runway_days']:g} days{before_rush}, and the meat delivery is a day late.", f"Order about {qty(beef['order_qty'])} kg today, or confirm the late delivery.", "urgent", "Protects Beef pilau sales"),
                   *([_alert("soon-out", f"{len(others_soon)} more ingredients run out within {SOON_DAYS:g} days", f"{', '.join(x['name'] for x in others_soon)}. They run out {('on ' + others_soon[0]['runs_out_day']) if others_soon[0]['runs_out_day'] == others_soon[-1]['runs_out_day'] else ('between ' + others_soon[0]['runs_out_day'] + ' and ' + others_soon[-1]['runs_out_day'])}, and {busy['day']} is expected to be your busiest day.", "Order them together with the beef so one delivery covers the week.", "watch")] if others_soon else []),
                   _alert("veg-expiry", "8 kg of vegetables need using", f"You use about {qty(veg['daily_use'])} kg of vegetables a day (about {veg_two_days:g} kg in two days), so the 8 kg near its date can be used in time.", "Put the older vegetables at the front and feature the vegetable bowl.", "watch", money(opps['waste']['value']) + " at risk", repeat_of="waste")],
        decisions=[_decision("Order beef today", f"With the sales we expect, beef runs out on {beef['runs_out_day']}{before_rush}. Beef pilau sells {pilau['units']} plates a day.", f"Place an order for about {qty(beef['order_qty'])} kg and ask for the earliest slot.", "Avoids running out of your best-loved dish"),
                   _decision("Send one combined order for what runs out this week", f"{to_order_n} ingredients will run out within the week. Ordering them together per supplier saves calls and delivery trips.", "Use the suggested order list on the Purchasing page.", "Avoids running out during your busy days"),
                   _decision("Use the older vegetables first", f"8 kg is close to its date but the kitchen normally uses {veg_two_days:g} kg in two days.", "Cook from the oldest batch first and run a vegetable bowl special.", money(opps['waste']['value']) + " potential saving")],
        charts=[dict(type="meters", title="How long each ingredient will last with the sales we expect", unit="days", target=LOW_COVER_DAYS,
                     items=[dict(label=x["name"], value=min(x["runway_days"], 7), note=f"{qty(x['on_hand'])} {x['unit']} on hand" + (f" · runs out {x['runs_out_day']}" if x["runs_out_day"] else " · more than 7 days"), status="low" if x["runway_days"] <= LOW_COVER_DAYS else ("watch" if x["runway_days"] <= SOON_DAYS or x["near_expiry"] else "ok")) for x in sorted(s["stock"], key=lambda z: z["runway_days"])])]),
      "bookings": dict(
        subtitle="Who is booked, and how busy the evening will be.",
        headline=f"{COVERS_TODAY} guests are expected tonight. One booking is still waiting for confirmation and {WAITLIST} tables are on the waitlist.",
        how_to_read="Covers means guests, not tables. The no-show rate is how often booked guests do not turn up, based on the sample history.",
        metrics=[('Expected covers', COVERS_TODAY), ('Waitlist', WAITLIST), ('No-show assumption', f'{NO_SHOW_PCT}%')], columns=['Time', 'Covers', 'Status'],
        rows=[list(slot) for slot in BOOKING_SLOTS],
        table_title="Tonight's bookings", table_note="Confirmed bookings are safe to plan for; the last one still needs a reply.",
        action="Confirm the late booking and preserve capacity for walk-ins.",
        attention=[_alert("late-booking", f"The {late_time} booking is not confirmed", f"{late_covers} guests are waiting for a reply, and {WAITLIST} tables are on the waitlist.", "Confirm the booking, or give the table to the waitlist.", "watch")],
        decisions=[_decision(f"Confirm the {late_time} table today", f"An unconfirmed table of {late_covers} blocks seats another party could use.", "Call or message the guest now.", f"Fills up to {late_covers} seats"),
                   _decision(f"Open more bookings for {busy['day']}", f"We expect about {busy_row['covers']} guests on {busy['day']}, compared with {COVERS_TODAY} tonight.", "Let regulars know, and keep a few tables free for walk-ins.", "Fills your busiest day")],
        extra_tables=[day_table("Guests we expect", "Worked out from the sales we expect, assuming the same number of guests per shilling as today.", ['Day', 'Expected sales', 'Guests (covers)'], lambda r: [r['day'], money(r['revenue']), r['covers']])]),
      "team": dict(
        subtitle="Who is working, and whether the shifts match how busy you are.",
        headline=f"{SCHEDULED_TODAY} people are scheduled and {ON_SHIFT} are on shift. About {OVERTIME_HOURS} hours of overtime could be avoided (about {money(opps['labor']['value'])}).",
        how_to_read="Coverage is how many people are working in each part of the day. Overtime is extra paid time; moving a shift is usually cheaper than paying it.",
        metrics=[('Scheduled', SCHEDULED_TODAY), ('On shift', ON_SHIFT), ('Avoidable overtime', money(opps['labor']['value']))], columns=['Period', 'People working', 'What to do'],
        rows=[['Lunch', LUNCH_PEOPLE, 'Enough people'], ['Dinner', DINNER_PEOPLE, f'Move {OVERTIME_HOURS} hours from a quiet period']],
        table_title="Coverage through the day", table_note="Lunch has enough people; dinner, your busiest time, is thin.",
        action="Preview the roster adjustment; preserve service coverage.",
        attention=[_alert("dinner", "Dinner is under-staffed", f"Only {DINNER_PEOPLE} people cover dinner while lunch has {LUNCH_PEOPLE}.", f"Move {OVERTIME_HOURS} hours from the quiet period into dinner.", "watch", money(opps['labor']['value']) + " potential / day", repeat_of="labor")],
        decisions=[_decision("Move hours into the dinner rush", "Overtime is being paid while a quiet period is fully staffed.", f"Shift {OVERTIME_HOURS} hours from the quiet period to dinner.", money(opps['labor']['value']) + " potential / day"),
                   _decision(f"Plan {busy_row['people']} people for {busy['day']}", f"We expect about {money(busy_row['revenue'])} on {busy['day']}. At today's pace of {money(revenue // SCHEDULED_TODAY)} of sales per person, that needs about {busy_row['people']} people, and you have {SCHEDULED_TODAY} scheduled today.", "Ask for extra shifts early, and let the quietest day run lean.", "Covers your busiest day without overtime")],
        extra_tables=[day_table("How many people we suggest", f"Assumes the same sales per person as today ({money(revenue // SCHEDULED_TODAY)}).", ['Day', 'Expected sales', 'People needed', f'Compared with {SCHEDULED_TODAY} today'], lambda r: [r['day'], money(r['revenue']), r['people'], f"{r['people'] - SCHEDULED_TODAY:+d}"])]),
      "menu": dict(
        subtitle="What you sell, what it costs to make, and where the money is.",
        headline=f"{top['name']} earns the most for the business today ({money(top['contribution'])}). After ingredients, the menu leaves {money(margin)} of today's {money(revenue)}.",
        how_to_read="Contribution is what is left of the price after the cost of the ingredients. It pays for staff and running costs. A dish can sell well and still earn little.",
        metrics=[('Dishes', 6), ('Food cost', money(s['food_cost'])), ('Contribution', money(margin))], columns=['Dish', 'Price', 'Cost to make', 'Sold today', 'Kept per plate'],
        rows=[[d['name'], money(d['price']), money(d['cost']), d['units'], f"{money(d['price'] - d['cost'])} ({d['margin_pct']}%)"] for d in dishes],
        table_title="Your menu today", table_note="Kept per plate is the price minus the cost of ingredients; the % is that as a share of the price.",
        action="Test a pilau price change before committing; demand may change.",
        attention=[_alert("pilau-price", "Beef pilau may be underpriced", f"It is your best seller ({pilau['units']} plates) and keeps {money(pilau['price'] - pilau['cost'])} a plate.", "Compare the result of a small price rise below before you change anything.", "watch", money(opps['margin']['value']) + " potential / day", repeat_of="margin")],
        decisions=[_decision("Try a small pilau price rise", f"A KES 30 rise on {pilau['units']} plates is worth {money(opps['margin']['value'])} a day if customers still order the same.", "Try it in the price calculator on the Menu page to see what happens if a few customers leave.", money(opps['margin']['value']) + " potential / day"),
                   _decision("Promote the vegetable bowl", f"It keeps {dishes[3]['margin_pct']}% of its price, more than the main dishes.", "Suggest it as a side or a lunch special.", "Higher share kept per sale")],
        charts=[dict(type="meters", title="What each dish keeps per plate (KES)", unit="KES", items=[dict(label=d["name"], value=d["price"] - d["cost"], note=f"{d['margin_pct']}% of the price", status="ok") for d in sorted(dishes, key=lambda z: -(z['price'] - z['cost']))])]),
      "finance": dict(
        subtitle="Where today's money went, and what is left.",
        headline=f"Of {money(revenue)} sold today, {money(s['food_cost'])} paid for ingredients and {money(LABOR_KES + OTHER_COSTS_KES)} for staff and running costs, leaving about {money(surplus)}.",
        how_to_read="Contribution (sales minus ingredients) is not profit. Staff and running costs still have to come out of it. The last row is what remains.",
        metrics=[('Sales', money(revenue)), ('Food cost', money(s['food_cost'])), ('Contribution', money(margin))], columns=['Category', 'Amount'],
        rows=[['Sales', money(revenue)], ['Ingredients', money(s['food_cost'])], ['Staff', money(LABOR_KES)], ['Other running costs', money(OTHER_COSTS_KES)], ['What is left', money(surplus)]],
        table_title="Where the money went", table_note="A simple day summary. Real accounts would include more (rent, tax and so on).",
        action="Contribution is not net profit. Review operating costs and settlement separately.",
        attention=[_alert("unmatched", f"{money(UNMATCHED_KES)} of payments is not matched", "Money recorded as paid has not yet been matched to a settlement.", "Check the payment reference before treating it as a loss.", "watch")],
        decisions=[_decision("Watch the cost of ingredients", f"Ingredients take {food_pct}% of every shilling you sell.", "Look first at the dishes that keep the least per plate.", "Protects what is left after costs")],
        charts=[dict(type="donut", title="Where today's sales went", slices=[dict(label="Ingredients", value=s['food_cost']), dict(label="Staff", value=LABOR_KES), dict(label="Other running costs", value=OTHER_COSTS_KES), dict(label="What is left", value=surplus)])]),
      "expenses": dict(
        subtitle="What it costs to run the restaurant.",
        headline=f"Costs today are {money(s['food_cost'] + LABOR_KES + OTHER_COSTS_KES)}: ingredients {food_pct}% of sales, staff {labor_pct}% and other costs {round(OTHER_COSTS_KES / revenue * 100, 1)}%.",
        how_to_read="Each cost is shown as a share of today's sales so you can see which one grows fastest when sales are slow.",
        metrics=[('Food', money(s['food_cost'])), ('Staff', money(LABOR_KES)), ('Other', money(OTHER_COSTS_KES))], columns=['Cost', 'Amount', 'Share of sales'],
        rows=[['Ingredients', money(s['food_cost']), f"{food_pct}%"], ['Staff', money(LABOR_KES), f"{labor_pct}%"], ['Utilities and rent', money(OTHER_COSTS_KES), f"{round(OTHER_COSTS_KES / revenue * 100, 1)}%"]],
        table_title="Costs today", table_note="These are the sample restaurant's costs for the day.",
        action="Compare cost categories with sales; these are explicit scenario costs.",
        attention=[], decisions=[_decision("Cut waste before cutting staff", f"Ingredients are the biggest cost ({food_pct}%), and near-expiry vegetables are worth {money(opps['waste']['value'])}.", "Use the older vegetables first this week.", money(opps['waste']['value']) + " potential saving")],
        charts=[dict(type="donut", title="Costs by type", slices=[dict(label="Ingredients", value=s['food_cost']), dict(label="Staff", value=LABOR_KES), dict(label="Utilities and rent", value=OTHER_COSTS_KES)])]),
      "suppliers": dict(
        subtitle="Who supplies you, and how reliable they are.",
        headline=f"3 suppliers cover all {len(s['stock'])} ingredients. The meat and fish partner is one day late, which is why beef is running low.",
        how_to_read="Each supplier is matched to the ingredients they provide, so a late delivery links straight to the dishes it affects.",
        metrics=[('Suppliers', 3), ('Late deliveries', 1), ('Price change', '+5%')], columns=['Supplier', 'Supplies', 'Delivery', 'What to do'],
        rows=[['Produce partner', ', '.join(x['name'] for x in s['stock'] if x['supplier'] == 'Produce partner'), 'On time', 'Use near-expiry vegetables first'],
              ['Meat & fish partner', ', '.join(x['name'] for x in s['stock'] if x['supplier'] == 'Meat & fish partner'), '1 day late', 'Confirm delivery time'],
              ['Dry goods & dairy partner', ', '.join(x['name'] for x in s['stock'] if x['supplier'] == 'Dry goods & dairy partner'), 'On time', 'Review the 5% price rise']],
        table_title="Your suppliers", table_note="Supplies lists the ingredients from the stock page.",
        action="Check delivery reliability alongside purchase cost.",
        attention=[_alert("late-meat", "The meat and fish delivery is a day late", f"Beef, chicken and tilapia come from this supplier, and beef only covers {beef['cover_days']:g} days.", "Call for a delivery time today.", "urgent")],
        decisions=[_decision("Ask for a firm delivery time", "A late delivery is what pushes beef towards running out.", "Call the supplier and agree the earliest slot.", "Avoids running out of beef"),
                   _decision("Review the 5% price rise", "The dry goods partner raised prices 5%.", "Ask another supplier for a price on rice and oil to compare.", "A better price on rice and oil")]),
      "purchasing": dict(
        subtitle="What you have ordered and what still needs a decision.",
        headline=f"{len(PURCHASE_ORDERS)} purchase orders are open worth {money(po_first[2] + po_second[2])}. One is waiting for your approval and one is overdue.",
        how_to_read="A purchase order is what you have promised to buy. Approve it to place the order; overdue means the goods should already be here.",
        metrics=[('Open orders', len(PURCHASE_ORDERS)), ('Commitments', money(po_first[2] + po_second[2])), ('Overdue', 1)], columns=['Order', 'Supplier', 'Amount', 'State'],
        rows=[[number, supplier, money(amount), state] for number, supplier, amount, state in PURCHASE_ORDERS],
        table_title="Open purchase orders", table_note="Approve the first, chase the second.",
        action="Review stock cover before making a purchasing commitment.",
        attention=[_alert("po-overdue", f"{po_second[0]} is overdue", f"The meat and fish order ({money(po_second[2])}) should already be here.", "Chase the supplier; beef is running low.", "urgent"),
                   _alert("po-approve", f"{po_first[0]} needs your approval", f"{money(po_first[2])} of dry goods is waiting on you.", "Check what rice and oil you actually need, then approve.", "watch")],
        decisions=[_decision(f"Check stock before approving {po_first[0]}", f"Rice lasts about {rice['runway_days']:g} days with the sales we expect and cooking oil far longer.", "Approve a smaller order if you already have plenty.", "Avoids over-buying"),
                   _decision("Send the suggested orders", f"{to_order_n} ingredients run out within the week. The list below groups them by supplier and shows when each order is needed.", "Approve the list, starting with the meat and fish order.", "Avoids running out during your busy days")],
        extra_tables=[dict(title="Suggested order list", note="Worked out from your recipes and the sales we expect. Assumes a supplier needs about a day to deliver.", columns=['Supplier', 'What to order', 'Order by'], rows=order_list)]),
      "cash-reconciliation": dict(
        subtitle="Checking that the money in the till, M-Pesa and cards matches the sales.",
        headline=f"{money(revenue - UNMATCHED_KES)} of {money(revenue)} has been matched. {money(UNMATCHED_KES)} is still unmatched.",
        how_to_read="Matching means a sale has a payment behind it. An unmatched amount is usually a timing or reference problem, not theft.",
        metrics=[('Recorded', money(revenue)), ('Matched', money(revenue - UNMATCHED_KES)), ('Unmatched', money(UNMATCHED_KES))], columns=['Category', 'Amount'],
        rows=[['Matched payments', money(revenue - UNMATCHED_KES)], ['Unmatched payment', money(UNMATCHED_KES)]],
        table_title="Sales against payments", table_note="Everything should match by the end of the day.",
        action="Match the payment reference before treating a difference as a loss.",
        attention=[_alert("unmatched-pay", f"{money(UNMATCHED_KES)} does not match a sale", "One payment does not have a matching sale reference.", "Find the M-Pesa or card reference and match it.", "watch", repeat_of="unmatched")],
        decisions=[_decision("Match it at close of day", "Small differences are usually reference typos.", "Open the payment reference and pair it with the right sale.", f"Clears {money(UNMATCHED_KES)}")]),
      "pos": dict(
        subtitle="Sales by channel and what the tills are doing.",
        headline=f"{ORDERS_TODAY} orders went through: {channels[0]['value']} dine-in, {channels[1]['value']} takeaway and {channels[2]['value']} delivery, averaging {money(revenue // ORDERS_TODAY)} each.",
        how_to_read="Channels are how a customer ordered. A bigger share in one channel tells you where to put your staff and marketing.",
        metrics=[('Completed orders', ORDERS_TODAY), ('Channels', 3), ('Average order', money(revenue // ORDERS_TODAY))], columns=['Channel', 'Orders', 'Share'],
        rows=[[c['label'], c['value'], f"{round(c['value'] / ORDERS_TODAY * 100)}%"] for c in channels],
        table_title="Orders by channel", table_note=f"Share is that channel's part of all {ORDERS_TODAY} orders.",
        action="Compare service load by channel.",
        attention=[], decisions=[_decision("Build takeaway", f"Takeaway is already about {round(TAKEAWAY_TODAY / ORDERS_TODAY * 100)}% of orders and needs no extra table space.", "Offer a lunch takeaway combo.", "More sales without more seats")],
        charts=[dict(type="donut", title="Orders by channel", slices=[dict(label=c['label'], value=c['value']) for c in channels])]),
      "marketing": dict(
        subtitle="Bringing more guests, and bringing them back.",
        headline=f"{RETURNING_GUESTS} returning and {new_guests} new guests visited. There is one draft offer ready to review.",
        how_to_read="Returning guests are the easiest to sell to. An offer is only useful if you can measure what it earned.",
        metrics=[('Returning guests', RETURNING_GUESTS), ('New guests', new_guests), ('Draft offers', 1)], columns=['Audience', 'Idea', 'How to measure'],
        rows=[['Returning lunch guests', 'Vegetable bowl offer', 'Extra money earned per offer used']],
        table_title="Ideas in draft", table_note="Nothing is sent to guests from this demonstration.",
        action="Preview an offer; no messages are sent from this demonstration.",
        attention=[], decisions=[_decision("Offer the vegetable bowl to regulars", f"It keeps {dishes[3]['margin_pct']}% of its price and uses vegetables that need using.", "Send a lunch offer to returning guests.", "Uses near-expiry stock")]),
      "risk": dict(
        subtitle="Unusual activity that deserves a second look.",
        headline=f"2 things need review: an unmatched payment of {money(UNMATCHED_KES)} and one order voided after preparation. Nothing here is proof of wrongdoing.",
        how_to_read="A signal means something looks unusual. Check it, and only then decide if it is a mistake or a problem.",
        metrics=[('Review items', 2), ('Amount to check', money(UNMATCHED_KES)), ('Confirmed theft', 0)], columns=['Signal', 'Evidence', 'What to do'],
        rows=[['Unmatched payment', money(UNMATCHED_KES), 'Check the reference'], ['Order voided after preparation', '1 order', 'Ask why it was voided']],
        table_title="Signals to review", table_note="Reviewing is not accusing.",
        action="A signal needs review; it is not an accusation.",
        attention=[_alert("void", "An order was voided after it was cooked", "That food was made but not paid for.", "Ask the staff member for the reason.", "watch")],
        decisions=[_decision("Ask before assuming", "Most voids are honest mistakes.", "Talk to the person on shift and record the reason.", "Keeps trust with the team")]),
      "intelligence": dict(
        subtitle="The few decisions that matter most to you today.",
        headline=f"3 ideas are worth {money(roi(day)['potential_daily'])} a day if they all work. None of it has been earned yet; these are chances, not results.",
        how_to_read="Each idea shows the sum behind it (quantity × value) so you can check it yourself. Ideas are independent and are not promises.",
        metrics=[('Ideas', 3), ('Possible value each day', money(roi(day)['potential_daily'])), ('Already earned', money(0))], columns=['Idea', 'The sum', 'Possible value'],
        rows=[[x['title'], f"{x['quantity']} × {x['unit_value']}", money(x['value'])] for x in s['opportunities']],
        table_title="Ideas ranked by value", table_note="Value per day if the idea works as assumed.",
        action="Prioritise evidence-backed opportunities and compare scenarios before acting.",
        attention=[], decisions=[_decision(x['title'], x['why'], x['action'], f"{money(x['value'])} potential / day") for x in s['opportunities']]),
      "data-trust": dict(
        subtitle="Where these numbers come from, and how far to trust them.",
        headline="Everything in this demo comes from a made-up sample restaurant so you can see how it works. No real restaurant data is used or changed.",
        how_to_read="A real restaurant would connect its own till and records here. This page would then show how fresh and complete they are.",
        metrics=[('Source', 'Sample restaurant'), ('History', '56 days'), ('Real records changed', 0)], columns=['Check', 'Result'],
        rows=[['Where the numbers come from', 'A sample restaurant made for this demo'], ['How totals are calculated', 'By the system, the same way every time'], ['Who can see this', 'Only the Demo owner'], ['Connected till or app', 'Not in this demo']],
        table_title="What we checked", table_note="Plain answers to plain questions.",
        action="Keep illustrative evidence separate from actual restaurant performance.",
        attention=[], decisions=[]),
      "audit": dict(
        subtitle="A record of decisions, so you can see who decided what and why.",
        headline="3 suggestions have been prepared. Nothing has been changed and nothing has been sent to anyone.",
        how_to_read="Each line is a suggestion the system made and where it stands. In a real restaurant this is your trail of who approved what, and when.",
        metrics=[('Suggestions made', 3), ('Changes made', 0), ('Messages sent', 0)], columns=['What', 'Why it matters', 'Where it stands'],
        rows=[['Price proposal (pilau)', 'Could earn about ' + money(opps['margin']['value']) + ' a day', 'Preview only, nothing changed'], ['Stock review (vegetables)', 'Avoids throwing away ' + money(opps['waste']['value']), 'Waiting for the owner'], ['Roster proposal (dinner)', 'Could save about ' + money(opps['labor']['value']) + ' overtime a day', 'Preview only, nothing changed']],
        table_title="Recent decisions", table_note="Every line says what it is, why it matters and its status.",
        action="Review the reason and effect before an operational change.",
        attention=[], decisions=[]),
      "settings": dict(
        subtitle="How this restaurant is set up.",
        headline="Demo Restaurant works in Kenya shillings (KES) and Nairobi time. It is completely separate from other restaurants.",
        how_to_read="These are the basics the system needs to show your money and times correctly.",
        metrics=[('Restaurant', 'Demo Restaurant'), ('Currency', 'KES'), ('Timezone', 'Africa/Nairobi')], columns=['Setting', 'Value'],
        rows=[['Data', 'Sample restaurant (demo)'], ['Records changed by this demo', 'None'], ['AI writing', 'Always based on your numbers, with a limit on daily use']],
        table_title="Basics", table_note="Nothing here can be changed in the demo.",
        action="The demo is isolated from Vibanda and other restaurants.",
        attention=[], decisions=[]),
    }
    if key == "notifications":
        # The same list Home shows, so the two can never disagree. Built here (not in `specs`)
        # because attention_items() itself reads every other area.
        items = attention_items(day)
        everything = items["attention"] + items["watching"]
        urgent = [x for x in everything if x["level"] == "urgent"]
        specs["notifications"] = dict(
            subtitle="Everything asking for your attention, in one place.",
            headline=f"{len(everything)} things need your attention, {len(urgent)} of them urgent.",
            how_to_read="These are the same items as on the Home page. Acknowledging one here only marks it for this demo.",
            metrics=[('Need attention', len(everything)), ('Urgent', len(urgent)), ('Messages sent', 0)],
            columns=['Alert', 'Where', 'What to do'],
            rows=[[x['title'], x['domain'], x['what_to_do']] for x in everything],
            table_title="Open alerts", table_note="Nothing is sent to anyone from the demo.",
            action="Open the evidence and acknowledge the sample alert.",
            attention=[{k: x[k] for k in ("id", "title", "why", "what_to_do", "level", "impact")} for x in urgent[:3]],
            decisions=[])
    spec = specs[key]
    metrics = spec["metrics"]
    charts = list(spec.get("charts", []))
    if key == "revenue":
        charts.insert(0, dict(type="line_band", title="Sales: last 14 days and the next 7",
                              actual=[{"date": r["date"], "day": DAY_NAMES[date.fromisoformat(r["date"]).weekday()][:3], "revenue": r["revenue"]} for r in s["history"][-14:]],
                              forecast=[{"date": r["date"], "day": r["day"][:3], "revenue": r["revenue"], "low": r["low"], "high": r["high"]} for r in forecast]))
    opportunities = [x for x in s['opportunities'] if x['area'] == key or key == 'intelligence']
    return {"key": key, "title": AREAS[key], "subtitle": spec["subtitle"], "notice": NOTICE, "headline": spec["headline"],
            "how_to_read": spec["how_to_read"], "metrics": [{"label": k, "value": v} for k, v in metrics],
            "columns": spec["columns"], "rows": spec["rows"], "table_title": spec["table_title"], "table_note": spec["table_note"],
            "action": spec["action"], "opportunities": opportunities, "attention": spec["attention"], "decisions": spec["decisions"],
            "charts": charts, "extra_tables": spec.get("extra_tables", []),
            "forecast": forecast if key in ('revenue', 'orders', 'pos', 'intelligence') else [],
            "forecast_method": "We look at how each weekday has done over the last 8 weeks and expect a similar day. The band shows how far a normal day can move from that.",
            "trend": s['history'][-7:] if key in ('revenue', 'finance', 'pos', 'intelligence') else []}
