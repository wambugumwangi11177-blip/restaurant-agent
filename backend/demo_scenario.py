"""Small, deterministic demonstration. No database access or generated transactions.

Money is integer KES here (unlike operational cents APIs). All surfaces consume
this same scenario; projections and opportunities are never realised savings.
"""
from datetime import date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo
from statistics import mean, pstdev

VERSION = "owner-demo-v1"
NOTICE = "Illustrative demo · calculated from a compact sample scenario, not actual restaurant results."
AREAS = {
    "revenue": "Revenue", "orders": "Orders", "kitchen": "Kitchen", "stock": "Stock",
    "bookings": "Bookings", "team": "Team", "menu": "Menu & pricing", "finance": "Finance",
    "expenses": "Expenses", "suppliers": "Suppliers", "purchasing": "Purchasing",
    "cash-reconciliation": "Cash reconciliation", "pos": "Point of sale", "marketing": "Marketing",
    "risk": "Fraud and risk", "notifications": "Notifications", "intelligence": "Business intelligence",
    "data-trust": "Data trust", "audit": "Audit trail", "settings": "Restaurant settings",
}

def today():
    return datetime.now(ZoneInfo("Africa/Nairobi")).date()

@lru_cache(maxsize=2)
def scenario(day: date):
    # Eight repetitions of a weekly sales pattern, with a modest upward trend.
    # 56 aggregate rows, six dishes, three controllable opportunities. Zero DB rows.
    menu = [("Beef pilau", 650, 270, 24), ("Chicken rice", 750, 320, 20),
            ("Grilled fish", 950, 420, 12), ("Vegetable bowl", 450, 140, 18),
            ("Fresh juice", 250, 70, 30), ("Chai", 100, 25, 36)]
    base = sum(price * qty for _, price, _, qty in menu)
    pattern = [82, 88, 94, 100, 118, 135, 108]
    history = []
    for i in range(56):
        d = day - timedelta(days=55-i)
        revenue = base * pattern[d.weekday()] * (94 + i // 7) // 10000
        history.append({"date": d.isoformat(), "revenue": revenue, "orders": max(1, revenue // 900)})
    # Today's menu is the exact source for today's sales and cost totals.
    history[-1] = {"date": day.isoformat(), "revenue": base, "orders": 70}
    spread = round(pstdev([r["revenue"] for r in history]))
    forecast = []
    for offset in range(1, 8):
        d = day + timedelta(days=offset)
        values = [r["revenue"] for r in history if date.fromisoformat(r["date"]).weekday() == d.weekday()]
        estimate = round(mean(values))
        forecast.append({"date": d.isoformat(), "revenue": estimate, "low": max(0, estimate-spread), "high": estimate+spread})
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
    return {"history": history, "menu": menu, "forecast": forecast, "opportunities": opportunities,
            "food_cost": sum(cost * qty for _, _, cost, qty in menu)}

def roi(day=None):
    s = scenario(day or today())
    return {"opportunities": s["opportunities"], "potential_daily": sum(x["value"] for x in s["opportunities"]),
            "label": "Illustrative daily opportunity", "realised": 0,
            "assumption": "Independent scenario opportunities; not guaranteed or realised savings. No subscription ROI percentage is claimed without an actual fee."}

def report(period, day=None):
    day = day or today()
    s = scenario(day)
    start = {"daily": day, "weekly": day-timedelta(days=day.weekday()),
             "monthly": day.replace(day=1), "yearly": day.replace(month=1, day=1)}[period]
    rows = [r for r in s["history"] if r["date"] >= start.isoformat()]
    revenue, orders = sum(r["revenue"] for r in rows), sum(r["orders"] for r in rows)
    text = f"Illustrative {period} report: KES {revenue:,} revenue across {orders} orders. "
    text += f"Coverage: {rows[0]['date']} to {day.isoformat()} ({len(rows)} sample days). "
    text += "Prioritise expiry waste, menu contribution and overtime. Forecasts are estimates; savings have not been realised."
    return {"period": period, "range": f"{rows[0]['date']} – {day.isoformat()}", "revenue": revenue, "orders": orders,
            "top_items": [{"name": n, "qty": q, "sales_kes": p*q} for n,p,c,q in s["menu"]] if period == "daily" else [],
            "report_text": text, "llm_used": False, "coverage_days": len(rows), "notice": NOTICE}

def home(period="today", day=None):
    day = day or today()
    s = scenario(day)
    # The one-hour window is an explicit sample slice, never passed off as live.
    count = {"today": 1, "7d": 7, "30d": 30, "1h": 1}[period]
    rows = s["history"][-count:]
    revenue, orders = sum(r["revenue"] for r in rows), sum(r["orders"] for r in rows)
    if period == "1h":
        revenue, orders = revenue // 8, max(1, orders // 8)
    return {"restaurant_name": "Demo Restaurant", "greeting_date": day.isoformat(), "period": period,
      "unavailable_metrics": [], "data_provenance": {"notice": NOTICE, "latest_order_at": None},
      "revenue": {"revenue": revenue, "orders": orders, "avg_order": revenue/orders, "pace_projection": 0},
      "orders": {"revenue": revenue, "orders": orders, "delayed": 2, "active_now": 6, "split": {"dine_in": orders*45//70, "takeaway": orders*18//70, "delivery": orders-orders*45//70-orders*18//70}},
      "kitchen": {"avg_prep_min": 14, "delay_risk": 2, "bottleneck": "Grill station"},
      "stock": {"recorded_items": 12, "low_stock": [{"name": "Beef", "qty": 6}], "expiring_48h": ["Vegetables · 8 kg"], "waste_pct_week": 3.2},
      "bookings": {"covers_today": 42, "next_reservation_min": 45, "waitlist": 4, "no_show_pct": 6},
      "staff": {"scheduled": 8, "on_shift": 6, "overtime_risk": 3, "labor_cost_pct": round(10500/s['history'][-1]['revenue']*100,1)},
      "attention": [{"id": x['id'], "domain": AREAS[x['area']], "title": x['title'], "why": x['why'], "what_to_do": x['action'],
                     "impact": f"KES {x['value']:,} potential / day", "status": "open"} for x in s['opportunities']],
      "pulse": [{"domain": "Forecast", "headline": f"KES {sum(r['revenue'] for r in s['forecast']):,} next 7 days", "detail": "Calculated from 56 sample daily summaries; inspect the range in Revenue."},
                {"domain": "Cash control", "headline": "KES 1,200 settlement exception", "detail": "Investigate an unmatched payment; this is not proven loss or theft."}],
      "source_status": {k: {"state": "available", "recommendations": 1} for k in AREAS},
      "performance": {"revenue_trend": s['history'][-7:]}, "roi": roi(day)}

def area(key, day=None):
    day = day or today()
    s = scenario(day)
    revenue = s['history'][-1]['revenue']
    margin = revenue-s['food_cost']
    money = lambda v: f"KES {v:,}"
    # Each row is an explicit sample fact, with calculated financial totals.
    specs = {
      "revenue": ([('Revenue today',money(revenue)),('Orders',70),('Average order',money(revenue//70))], ['Day','Revenue','Orders'], [[r['date'],money(r['revenue']),r['orders']] for r in s['history'][-7:]], "Use the expected range to plan stock and staffing, then compare actual sales."),
      "orders": ([('Completed',70),('Open',6),('Delayed',2)], ['Ticket','Channel','State'], [['D-101','Dine-in','Preparing'],['D-102','Takeaway','Ready'],['D-103','Delivery','Delayed']], "Prioritise delayed tickets and review service time."),
      "kitchen": ([('Average prep','14 min'),('Open tickets',6),('Delayed',2)], ['Station','Prep time','Action'], [['Grill','22 min','Rebalance queue'],['Cold station','8 min','Support plating']], "Move plating support to the grill before the dinner rush."),
      "stock": ([('Tracked items',12),('Low stock',1),('Expiry exposure',money(1440))], ['Ingredient','On hand','Forward risk'], [['Beef','6 kg','2 days cover at 3 kg/day'],['Vegetables','8 kg','Use within 48h']], "Use expiry stock first and review beef replenishment."),
      "bookings": ([('Expected covers',42),('Waitlist',4),('No-show assumption','6%')], ['Time','Covers','Status'], [['18:00',12,'Confirmed'],['19:00',18,'Confirmed'],['20:00',12,'Awaiting confirmation']], "Confirm the late booking and preserve capacity for walk-ins."),
      "team": ([('Scheduled',8),('On shift',6),('Avoidable overtime',money(750))], ['Period','Coverage','Action'], [['Lunch',6,'Adequate'],['Dinner',4,'Move 3 hours from quiet period']], "Preview the roster adjustment; preserve service coverage."),
      "menu": ([('Dishes',6),('Food cost',money(s['food_cost'])),('Contribution',money(margin))], ['Dish','Price','Cost','Units'], [[n,money(p),money(c),q] for n,p,c,q in s['menu']], "Test a pilau price change before committing; demand may change."),
      "finance": ([('Sales',money(revenue)),('Food cost',money(s['food_cost'])),('Contribution',money(margin))], ['Category','Amount'], [['Sales',money(revenue)],['Food cost',money(s['food_cost'])],['Labor',money(10500)],['Other operating costs',money(6500)],['Operating surplus',money(margin-17000)]], "Contribution is not net profit. Review operating costs and settlement separately."),
      "expenses": ([('Food',money(s['food_cost'])),('Labor',money(10500)),('Other',money(6500))], ['Expense','Amount'], [['Ingredients',money(s['food_cost'])],['Labor',money(10500)],['Utilities / occupancy',money(6500)]], "Compare cost categories with sales; these are explicit scenario costs."),
      "suppliers": ([('Suppliers',3),('Late deliveries',1),('Price change','+5%')], ['Supplier','Delivery','Next step'], [['Produce partner','On time','Use expiry stock first'],['Meat partner','1 day late','Confirm ETA'],['Dry goods partner','On time','Review price increase']], "Check delivery reliability alongside purchase cost."),
      "purchasing": ([('Open orders',2),('Commitments',money(18000)),('Overdue',1)], ['Order','Amount','State'], [['PO-D1',money(12000),'Awaiting approval'],['PO-D2',money(6000),'Delivery overdue']], "Review stock cover before making a purchasing commitment."),
      "cash-reconciliation": ([('Recorded',money(revenue)),('Settled',money(revenue-1200)),('Unmatched',money(1200))], ['Category','Amount'], [['Matched payments',money(revenue-1200)],['Unmatched payment',money(1200)]], "Match the payment reference before treating a difference as a loss."),
      "pos": ([('Completed orders',70),('Channels',3),('Average order',money(revenue//70))], ['Channel','Orders'], [['Dine-in',45],['Takeaway',18],['Delivery',7]], "Compare service load by channel."),
      "marketing": ([('Returning guests',28),('New guests',42),('Draft offers',1)], ['Audience','Idea','Measurement'], [['Returning lunch guests','Vegetable bowl offer','Contribution per redeemed offer']], "Preview an offer; no messages are sent from this demonstration."),
      "risk": ([('Review items',2),('Settlement exposure',money(1200)),('Confirmed theft',0)], ['Signal','Evidence','Next step'], [['Unmatched payment',money(1200),'Check reference'],['Void after preparation','1 sample event','Review reason']], "A signal needs review; it is not an accusation."),
      "notifications": ([('Attention items',3),('Urgent',1),('External sends',0)], ['Alert','Action'], [[x['title'],x['action']] for x in s['opportunities']], "Open the evidence and acknowledge the sample alert."),
      "intelligence": ([('Opportunities',3),('Potential daily value',money(roi(day)['potential_daily'])),('Realised savings',money(0))], ['Opportunity','Calculation','Potential'], [[x['title'],f"{x['quantity']} × {x['unit_value']}",money(x['value'])] for x in s['opportunities']], "Prioritise evidence-backed opportunities and compare scenarios before acting."),
      "data-trust": ([('Source','Illustrative sample'),('History','56 daily summaries'),('Business rows added',0)], ['Check','Result'], [['Financial arithmetic','Calculated in Python'],['Tenant scope','Authenticated Demo only'],['External POS integration','Not claimed']], "Keep illustrative evidence separate from actual restaurant performance."),
      "audit": ([('Sample decisions',3),('Business writes',0),('External actions',0)], ['Sample event','State'], [['Price proposal','Preview only'],['Stock review','Awaiting owner'],['Roster proposal','Preview only']], "Review the reason and effect before an operational change."),
      "settings": ([('Restaurant','Demo Restaurant'),('Currency','KES'),('Timezone','Africa/Nairobi')], ['Control','Value'], [['Dataset',VERSION],['Business persistence','None'],['AI output','Grounded, metered and cached']], "The demo is isolated from Vibanda and other restaurants."),
    }
    metrics, columns, rows, action = specs[key]
    opportunities = [x for x in s['opportunities'] if x['area'] == key or key == 'intelligence']
    return {"key": key, "title": AREAS[key], "notice": NOTICE, "metrics": [{"label": k,"value": v} for k,v in metrics],
            "columns": columns,"rows": rows,"action": action,"opportunities": opportunities,
            "forecast": s['forecast'] if key in ('revenue','orders','pos','intelligence') else [],
            "forecast_method": "Weekday mean over 8 sample weeks; range is ± one sample standard deviation, not a calibrated probability.",
            "trend": s['history'][-7:] if key in ('revenue','finance','pos','intelligence') else []}
