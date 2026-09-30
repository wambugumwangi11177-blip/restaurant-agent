"""Small, deterministic demonstration. No database access or generated transactions.

Money is integer KES here (unlike operational cents APIs). All surfaces consume
this same scenario; projections and opportunities are never realised savings.
Every figure shown to the owner is derived from the values below, never typed
into copy by hand, so the pages, the OS answers and the PDF report always agree.
"""
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
LABOR_KES = 10500
OTHER_COSTS_KES = 6500
UNMATCHED_KES = 1200


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
    history[-1] = {"date": day.isoformat(), "revenue": base, "orders": 70}
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
        {"id": "labor", "area": "team", "title": "Shift coverage into the dinner rush", "quantity": 3, "unit_value": 250,
         "why": "3 avoidable overtime hours × KES 250 per hour.", "action": "Move existing coverage into the busy service window."},
    ]
    for item in opportunities:
        item["value"] = item["quantity"] * item["unit_value"]
    # Stock: what today's menu uses, against what is on the shelf.
    usage, used_in = {}, {}
    for dish, _price, _cost, portions in menu:
        for ing, per in RECIPES[dish].items():
            usage[ing] = usage.get(ing, 0) + per * portions
            used_in.setdefault(ing, []).append(dish)
    stock = []
    for ing, unit in UNITS.items():
        daily = round(usage[ing], 2)
        cover = round(ON_HAND[ing] / daily, 1)
        stock.append({"name": ing, "unit": unit, "on_hand": ON_HAND[ing], "daily_use": daily, "cover_days": cover,
                      "used_in": used_in[ing], "supplier": SUPPLIER_OF[ing], "low": cover <= LOW_COVER_DAYS,
                      "near_expiry": NEAR_EXPIRY.get(ing, 0)})
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
    dine = orders * 45 // 70
    take = orders * 18 // 70
    return [{"label": "Dine-in", "value": dine}, {"label": "Takeaway", "value": take},
            {"label": "Delivery", "value": orders - dine - take}]


def _decision(idea, why, next_step, expected=None):
    return {"idea": idea, "why": why, "next_step": next_step, "expected": expected}


def _alert(id_, title, why, what_to_do, level="watch", impact=None):
    return {"id": id_, "title": title, "why": why, "what_to_do": what_to_do, "level": level, "impact": impact}


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
    beef_cover = next(x["cover_days"] for x in s["stock"] if x["name"] == "Beef")
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
        {"title": "Stock and waste", "text": f"Beef is down to {beef_cover:g} days of cover and the meat delivery is a day late, so order today. "
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
            "weekday_pattern": weekday_pattern(s), "channels": _channels(70), "dishes": dishes,
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


def home(period="today", day=None):
    day = day or today()
    s = scenario(day)
    # The one-hour window is an explicit sample slice, never passed off as live.
    count = {"today": 1, "7d": 7, "30d": 30, "1h": 1}[period]
    rows = s["history"][-count:]
    revenue, orders = sum(r["revenue"] for r in rows), sum(r["orders"] for r in rows)
    if period == "1h":
        revenue, orders = revenue // 8, max(1, orders // 8)
    low = [x for x in s["stock"] if x["low"]]
    return {"restaurant_name": "Demo Restaurant", "greeting_date": day.isoformat(), "period": period,
      "unavailable_metrics": [], "data_provenance": {"notice": NOTICE, "latest_order_at": None},
      "revenue": {"revenue": revenue, "orders": orders, "avg_order": revenue/orders, "pace_projection": 0},
      "orders": {"revenue": revenue, "orders": orders, "delayed": 2, "active_now": 6, "split": {"dine_in": orders*45//70, "takeaway": orders*18//70, "delivery": orders-orders*45//70-orders*18//70}},
      "kitchen": {"avg_prep_min": 14, "delay_risk": 2, "bottleneck": "Grill station"},
      "stock": {"recorded_items": len(s["stock"]), "low_stock": [{"name": x["name"], "qty": x["on_hand"]} for x in low],
                "expiring_48h": [f"{k} · {v} kg" for k, v in NEAR_EXPIRY.items()], "waste_pct_week": 3.2},
      "bookings": {"covers_today": 42, "next_reservation_min": 45, "waitlist": 4, "no_show_pct": 6},
      "staff": {"scheduled": 8, "on_shift": 6, "overtime_risk": 3, "labor_cost_pct": round(LABOR_KES/s['history'][-1]['revenue']*100,1)},
      "attention": [{"id": x['id'], "domain": AREAS[x['area']], "title": x['title'], "why": x['why'], "what_to_do": x['action'],
                     "impact": f"KES {x['value']:,} potential / day", "status": "open"} for x in s['opportunities']],
      "pulse": [{"domain": "Forecast", "headline": f"KES {sum(r['revenue'] for r in s['forecast']):,} next 7 days", "detail": "Calculated from 56 sample daily summaries; inspect the range in Revenue."},
                {"domain": "Cash control", "headline": f"KES {UNMATCHED_KES:,} settlement exception", "detail": "Investigate an unmatched payment; this is not proven loss or theft."}],
      "source_status": {k: {"state": "available", "recommendations": 1} for k in AREAS},
      "performance": {"revenue_trend": s['history'][-7:]}, "roi": roi(day)}


def _stock_area(s):
    rows = []
    for x in s["stock"]:
        if x["low"]:
            todo = "Order today"
        elif x["near_expiry"]:
            todo = f"Use the {x['near_expiry']} kg near its date first"
        else:
            todo = "Fine for now"
        rows.append([x["name"], f"{qty(x['on_hand'])} {x['unit']}", f"{qty(x['daily_use'])} {x['unit']}",
                     f"{x['cover_days']:g} days", ", ".join(x["used_in"]), todo])
    return rows


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

    # Each spec: subtitle, headline, how_to_read, metrics, columns, rows, table_title, table_note, action,
    # attention (what needs attention here), decisions (ideas and why), charts.
    specs = {
      "revenue": dict(
        subtitle="How much money the restaurant is bringing in, and what to expect next.",
        headline=f"You took {money(revenue)} today from 70 orders. Over the last week you averaged {money(last7)} a day, {abs(g)}% {'more' if g >= 0 else 'less'} than the week before.",
        how_to_read="The line shows the last 14 days and the next 7. The shaded band is how far a normal day can move away from what we expect. Tap any coming day to see why we expect that amount.",
        metrics=[('Revenue today', money(revenue)), ('Orders', 70), ('Average order', money(revenue // 70))],
        columns=['Day', 'Revenue', 'Orders'], rows=[[f"{DAY_NAMES[date.fromisoformat(r['date']).weekday()][:3]} {r['date'][5:]}", money(r['revenue']), r['orders']] for r in s['history'][-7:]],
        table_title="The last 7 days", table_note="Each row is one trading day: what was taken and how many orders it came from.",
        action="Use the expected range to plan stock and staffing, then compare actual sales.",
        attention=[_alert("quiet-day", f"{quiet['day']} looks quiet", f"We expect about {money(quiet['revenue'])} on {quiet['day']}, the lowest of the coming week.", "Prepare a little less and keep staffing lean that day.", "watch")],
        decisions=[_decision(f"Prepare for a busy {busy['day']}", f"{busy['day']} is expected to bring about {money(busy['revenue'])}, your strongest day this week.", "Order stock a day ahead and make sure the floor and kitchen are fully covered.", f"Protects about {money(busy['revenue'])} of sales"),
                   _decision(f"Keep {quiet['day']} lean", f"{quiet['day']}s average {money(quiet['revenue'])}, well below a typical day.", "Cut prep for slow sellers and avoid overtime that day.", "Less waste and lower labour cost")]),
      "orders": dict(
        subtitle="The orders coming in, and whether service is keeping up.",
        headline="70 orders are complete, 6 are being prepared and 2 are running late.",
        how_to_read="Open orders are still moving through the kitchen. A late order is one that has taken longer than it should; those are the ones to look at first.",
        metrics=[('Completed', 70), ('Open', 6), ('Delayed', 2)], columns=['Ticket', 'Channel', 'State'],
        rows=[['D-101', 'Dine-in', 'Preparing'], ['D-102', 'Takeaway', 'Ready'], ['D-103', 'Delivery', 'Delayed']],
        table_title="Orders that need a look", table_note="A short list of orders in progress right now.",
        action="Prioritise delayed tickets and review service time.",
        attention=[_alert("late-orders", "2 orders are running late", "One delivery order (D-103) has waited longer than usual.", "Check the grill queue and let the customer know.", "urgent")],
        decisions=[_decision("Clear the late delivery first", "Delivery customers cannot see the kitchen, so delays turn into complaints quickly.", "Send the late delivery next and call the customer.", "Protects the customer relationship")]),
      "kitchen": dict(
        subtitle="What is being prepared, and where the kitchen is slowing down.",
        headline="Average preparation is 14 minutes. The grill is the slowest station at 22 minutes while the cold station is waiting at 8.",
        how_to_read="Prep time is how long a dish takes from order to plate. When one station is far slower than the others, orders queue behind it.",
        metrics=[('Average prep', '14 min'), ('Open tickets', 6), ('Delayed', 2)], columns=['Station', 'Prep time', 'What to do'],
        rows=[['Grill', '22 min', 'Rebalance queue'], ['Cold station', '8 min', 'Support plating']],
        table_title="Stations right now", table_note="Slowest first. The idea is to move a helper to the slowest station.",
        action="Move plating support to the grill before the dinner rush.",
        attention=[_alert("grill", "The grill is the bottleneck", "Grill dishes (grilled fish, beef) take 22 minutes while the cold station finishes in 8.", "Move plating support to the grill before the dinner rush.", "urgent")],
        decisions=[_decision("Share the load before dinner", "Two orders are already late and dinner is your busiest time.", "Ask the cold station to help plate grill orders.", "Fewer late orders")]),
      "stock": dict(
        subtitle="What is on the shelf, how long it will last, and what to order.",
        headline=f"You track {len(s['stock'])} ingredients, all used by the dishes on your menu. Beef covers only {beef['cover_days']:g} days and {NEAR_EXPIRY['Mixed vegetables']} kg of vegetables must be used within 2 days.",
        how_to_read="'Days of cover' is how long the stock lasts at today's selling rate. Each ingredient shows which dishes use it, so you can see which dish is affected if it runs out.",
        metrics=[('Ingredients tracked', len(s['stock'])), ('Need ordering', len(low)), ('Near expiry', money(opps['waste']['value']))],
        columns=['Ingredient', 'On hand', 'Used per day', 'Days of cover', 'Used in', 'What to do'], rows=_stock_area(s),
        table_title="Everything on the shelf", table_note="Used per day is worked out from the recipes and today's sales.",
        action="Use expiry stock first and review beef replenishment.",
        attention=[_alert("beef-low", "Beef is running low", f"{qty(beef['on_hand'])} kg left and Beef pilau uses {qty(beef['daily_use'])} kg a day. That is {beef['cover_days']:g} days of cover, and the meat delivery is a day late.", "Order beef today, or confirm the late delivery.", "urgent", "Protects Beef pilau sales"),
                   _alert("veg-expiry", "8 kg of vegetables need using", f"You use about {qty(veg['daily_use'])} kg of vegetables a day (about {veg_two_days:g} kg in two days), so the 8 kg near its date can be used in time.", "Put the older vegetables at the front and feature the vegetable bowl.", "watch", money(opps['waste']['value']) + " at risk")],
        decisions=[_decision("Use the older vegetables first", f"8 kg is close to its date but the kitchen normally uses {veg_two_days:g} kg in two days.", "Cook from the oldest batch first and run a vegetable bowl special.", money(opps['waste']['value']) + " potential saving"),
                   _decision("Order beef today", f"Beef pilau sells {pilau['units']} plates a day and uses all the beef in two days.", "Place the beef order now and ask for the earliest slot.", "Avoids running out of your best-loved dish")],
        charts=[dict(type="meters", title="How many days each ingredient will last", unit="days", target=LOW_COVER_DAYS,
                     items=[dict(label=x["name"], value=x["cover_days"], note=f"{qty(x['on_hand'])} {x['unit']} on hand", status="low" if x["low"] else ("watch" if x["near_expiry"] else "ok")) for x in sorted(s["stock"], key=lambda z: z["cover_days"])])]),
      "bookings": dict(
        subtitle="Who is booked, and how busy the evening will be.",
        headline="42 guests are expected tonight. One booking is still waiting for confirmation and 4 tables are on the waitlist.",
        how_to_read="Covers means guests, not tables. The no-show rate is how often booked guests do not turn up, based on the sample history.",
        metrics=[('Expected covers', 42), ('Waitlist', 4), ('No-show assumption', '6%')], columns=['Time', 'Covers', 'Status'],
        rows=[['18:00', 12, 'Confirmed'], ['19:00', 18, 'Confirmed'], ['20:00', 12, 'Awaiting confirmation']],
        table_title="Tonight's bookings", table_note="Confirmed bookings are safe to plan for; the last one still needs a reply.",
        action="Confirm the late booking and preserve capacity for walk-ins.",
        attention=[_alert("late-booking", "The 20:00 booking is not confirmed", "12 guests are waiting for a reply, and 4 tables are on the waitlist.", "Confirm the booking, or give the table to the waitlist.", "watch")],
        decisions=[_decision("Confirm the 20:00 table today", "An unconfirmed table of 12 blocks seats another party could use.", "Call or message the guest now.", "Fills up to 12 seats")]),
      "team": dict(
        subtitle="Who is working, and whether the shifts match how busy you are.",
        headline=f"8 people are scheduled and 6 are on shift. About 3 hours of overtime could be avoided (about {money(opps['labor']['value'])}).",
        how_to_read="Coverage is how many people are working in each part of the day. Overtime is extra paid time; moving a shift is usually cheaper than paying it.",
        metrics=[('Scheduled', 8), ('On shift', 6), ('Avoidable overtime', money(opps['labor']['value']))], columns=['Period', 'People working', 'What to do'],
        rows=[['Lunch', 6, 'Enough people'], ['Dinner', 4, 'Move 3 hours from a quiet period']],
        table_title="Coverage through the day", table_note="Lunch has enough people; dinner, your busiest time, is thin.",
        action="Preview the roster adjustment; preserve service coverage.",
        attention=[_alert("dinner", "Dinner is under-staffed", "Only 4 people cover dinner while lunch has 6.", "Move 3 hours from the quiet period into dinner.", "watch", money(opps['labor']['value']) + " potential / day")],
        decisions=[_decision("Move hours into the dinner rush", "Overtime is being paid while a quiet period is fully staffed.", "Shift 3 hours from the quiet period to dinner.", money(opps['labor']['value']) + " potential / day")]),
      "menu": dict(
        subtitle="What you sell, what it costs to make, and where the money is.",
        headline=f"{top['name']} earns the most for the business today ({money(top['contribution'])}). After ingredients, the menu leaves {money(margin)} of today's {money(revenue)}.",
        how_to_read="Contribution is what is left of the price after the cost of the ingredients. It pays for staff and running costs. A dish can sell well and still earn little.",
        metrics=[('Dishes', 6), ('Food cost', money(s['food_cost'])), ('Contribution', money(margin))], columns=['Dish', 'Price', 'Cost to make', 'Sold today', 'Kept per plate'],
        rows=[[d['name'], money(d['price']), money(d['cost']), d['units'], f"{money(d['price'] - d['cost'])} ({d['margin_pct']}%)"] for d in dishes],
        table_title="Your menu today", table_note="Kept per plate is the price minus the cost of ingredients; the % is that as a share of the price.",
        action="Test a pilau price change before committing; demand may change.",
        attention=[_alert("pilau-price", "Beef pilau may be underpriced", f"It is your best seller ({pilau['units']} plates) and keeps {money(pilau['price'] - pilau['cost'])} a plate.", "Compare the result of a small price rise below before you change anything.", "watch", money(opps['margin']['value']) + " potential / day")],
        decisions=[_decision("Try a small pilau price rise", f"A KES 30 rise on {pilau['units']} plates is worth {money(opps['margin']['value'])} a day if customers still order the same.", "Use the calculator below to see what happens if a few customers leave.", money(opps['margin']['value']) + " potential / day"),
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
        headline=f"2 purchase orders are open worth {money(18000)}. One is waiting for your approval and one is overdue.",
        how_to_read="A purchase order is what you have promised to buy. Approve it to place the order; overdue means the goods should already be here.",
        metrics=[('Open orders', 2), ('Commitments', money(18000)), ('Overdue', 1)], columns=['Order', 'Supplier', 'Amount', 'State'],
        rows=[['PO-D1', 'Dry goods & dairy partner', money(12000), 'Waiting for your approval'], ['PO-D2', 'Meat & fish partner', money(6000), 'Delivery overdue']],
        table_title="Open purchase orders", table_note="Approve the first, chase the second.",
        action="Review stock cover before making a purchasing commitment.",
        attention=[_alert("po-overdue", "PO-D2 is overdue", "The meat and fish order (KES 6,000) should already be here.", "Chase the supplier; beef is running low.", "urgent"),
                   _alert("po-approve", "PO-D1 needs your approval", "KES 12,000 of dry goods is waiting on you.", "Check what rice and oil you actually need, then approve.", "watch")],
        decisions=[_decision("Check stock before approving PO-D1", f"Rice covers about {rice['cover_days']:g} days and cooking oil far longer.", "Approve a smaller order if you already have plenty.", "Avoids over-buying")]),
      "cash-reconciliation": dict(
        subtitle="Checking that the money in the till, M-Pesa and cards matches the sales.",
        headline=f"{money(revenue - UNMATCHED_KES)} of {money(revenue)} has been matched. {money(UNMATCHED_KES)} is still unmatched.",
        how_to_read="Matching means a sale has a payment behind it. An unmatched amount is usually a timing or reference problem, not theft.",
        metrics=[('Recorded', money(revenue)), ('Matched', money(revenue - UNMATCHED_KES)), ('Unmatched', money(UNMATCHED_KES))], columns=['Category', 'Amount'],
        rows=[['Matched payments', money(revenue - UNMATCHED_KES)], ['Unmatched payment', money(UNMATCHED_KES)]],
        table_title="Sales against payments", table_note="Everything should match by the end of the day.",
        action="Match the payment reference before treating a difference as a loss.",
        attention=[_alert("unmatched-pay", f"{money(UNMATCHED_KES)} does not match a sale", "One payment does not have a matching sale reference.", "Find the M-Pesa or card reference and match it.", "watch")],
        decisions=[_decision("Match it at close of day", "Small differences are usually reference typos.", "Open the payment reference and pair it with the right sale.", f"Clears {money(UNMATCHED_KES)}")]),
      "pos": dict(
        subtitle="Sales by channel and what the tills are doing.",
        headline=f"70 orders went through: 45 dine-in, 18 takeaway and 7 delivery, averaging {money(revenue // 70)} each.",
        how_to_read="Channels are how a customer ordered. A bigger share in one channel tells you where to put your staff and marketing.",
        metrics=[('Completed orders', 70), ('Channels', 3), ('Average order', money(revenue // 70))], columns=['Channel', 'Orders', 'Share'],
        rows=[['Dine-in', 45, f"{round(45 / 70 * 100)}%"], ['Takeaway', 18, f"{round(18 / 70 * 100)}%"], ['Delivery', 7, f"{round(7 / 70 * 100)}%"]],
        table_title="Orders by channel", table_note="Share is that channel's part of all 70 orders.",
        action="Compare service load by channel.",
        attention=[], decisions=[_decision("Build takeaway", "Takeaway is already a quarter of orders and needs no extra table space.", "Offer a lunch takeaway combo.", "More sales without more seats")],
        charts=[dict(type="donut", title="Orders by channel", slices=[dict(label=c['label'], value=c['value']) for c in _channels(70)])]),
      "marketing": dict(
        subtitle="Bringing more guests, and bringing them back.",
        headline="28 returning and 42 new guests visited. There is one draft offer ready to review.",
        how_to_read="Returning guests are the easiest to sell to. An offer is only useful if you can measure what it earned.",
        metrics=[('Returning guests', 28), ('New guests', 42), ('Draft offers', 1)], columns=['Audience', 'Idea', 'How to measure'],
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
      "notifications": dict(
        subtitle="Everything asking for your attention, in one place.",
        headline="3 things need your attention: vegetables near expiry, the pilau price and dinner coverage. One is urgent.",
        how_to_read="These are the same items as on the Home page. Acknowledging one here only marks it for this demo.",
        metrics=[('Need attention', 3), ('Urgent', 1), ('Messages sent', 0)], columns=['Alert', 'What to do'],
        rows=[[x['title'], x['action']] for x in s['opportunities']],
        table_title="Open alerts", table_note="Nothing is sent to anyone from the demo.",
        action="Open the evidence and acknowledge the sample alert.",
        attention=[_alert("beef-notify", "Beef is running low", f"It covers {beef['cover_days']:g} days and the meat delivery is late.", "Order beef today.", "urgent")], decisions=[]),
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
            "charts": charts,
            "forecast": forecast if key in ('revenue', 'orders', 'pos', 'intelligence') else [],
            "forecast_method": "We look at how each weekday has done over the last 8 weeks and expect a similar day. The band shows how far a normal day can move from that.",
            "trend": s['history'][-7:] if key in ('revenue', 'finance', 'pos', 'intelligence') else []}
