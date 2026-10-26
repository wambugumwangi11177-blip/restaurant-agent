"""One specific, plain-language answer for each prompted question in the Demo Restaurant OS.

Every figure is read from the demo scenario (demo_scenario.py), never typed here, so an answer can
never disagree with the pages. A question is matched by its exact wording and not by keywords, so an
answer cannot be about the wrong ingredient, dish or day. A typed question that is not in this list
keeps the general answer for its area. The list must match frontend/src/lib/demoQuestions.ts; a test
reads that file and fails if the two drift apart.
"""
import re

import demo_scenario as demo
from demo_scenario import money, qty

_ANSWERS = {}


def _normal(question):
    return re.sub(r"\s+", " ", question or "").strip().rstrip("?").strip().casefold()


def _ask(area, question):
    def register(fn):
        key = _normal(question)
        if key in _ANSWERS:
            raise ValueError(f"two answers for: {question}")
        _ANSWERS[key] = (area, fn)
        return fn
    return register


def known_questions():
    """{normalised question: area slug}, so a test can compare it with the questions on screen."""
    return {key: area for key, (area, _fn) in _ANSWERS.items()}


def normalise(question):
    return _normal(question)


def area_of(question):
    entry = _ANSWERS.get(_normal(question))
    return entry[0] if entry else None


def answer_for(question, day=None):
    """The specific answer to a prompted question, or None when the question is not one of them."""
    entry = _ANSWERS.get(_normal(question))
    if entry is None:
        return None
    return entry[1](_Context(day or demo.today()))


class _Context:
    """Everything an answer may quote, taken from the scenario and the area pages."""

    def __init__(self, day):
        self.day = day
        s = self.s = demo.scenario(day)
        self.revenue = s["history"][-1]["revenue"]
        self.food = s["food_cost"]
        self.contribution = self.revenue - self.food
        self.surplus = self.contribution - demo.LABOR_KES - demo.OTHER_COSTS_KES
        self.last7, self.before7, self.growth = demo.growth(s)
        self.dish_list = demo._dish_rows(s)
        self.dishes = {d["name"]: d for d in self.dish_list}
        self.plates_today = sum(d["units"] for d in self.dish_list)
        self.stock = {x["name"]: x for x in s["stock"]}
        self.forecast = s["forecast"]
        self.by_day = {r["day"]: r for r in self.forecast}
        self.busy = max(self.forecast, key=lambda r: r["revenue"])
        self.quiet = min(self.forecast, key=lambda r: r["revenue"])
        self.opps = {o["id"]: o for o in s["opportunities"]}
        self.roi = demo.roi(day)
        self.channels = demo._channels(demo.ORDERS_TODAY)
        self.food_pct = round(self.food / self.revenue * 100, 1)
        self.labor_pct = round(demo.LABOR_KES / self.revenue * 100, 1)
        self.other_pct = round(demo.OTHER_COSTS_KES / self.revenue * 100, 1)
        self.surplus_pct = round(self.surplus / self.revenue * 100, 1)
        self.soon = sorted((x for x in s["stock"] if x["runway_days"] <= demo.SOON_DAYS), key=lambda z: z["runway_days"])
        self.to_order = [x for x in s["stock"] if x["order_qty"] > 0]
        self.order_list = demo._order_list(s)
        self.late_time, self.late_covers, _late_state = next(b for b in demo.BOOKING_SLOTS if b[2] != "Confirmed")
        self.po_first, self.po_second = demo.PURCHASE_ORDERS
        self.po_total = sum(p[2] for p in demo.PURCHASE_ORDERS)

    def area(self, key):
        return demo.area(key, self.day)

    def alert(self, key, alert_id):
        return next(a for a in self.area(key)["attention"] if a["id"] == alert_id)

    def metrics(self, key):
        return {m["label"]: m["value"] for m in self.area(key)["metrics"]}

    def share(self, part):
        return round(part / demo.ORDERS_TODAY * 100)


def _list(items):
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _lc(text):
    """Lower-case a title's first letter so it reads inside a sentence, unless it starts with a code or acronym."""
    return text[0].lower() + text[1:] if len(text) > 1 and text[1].islower() else text


def _when(x):
    """'today' or 'by Friday', for when an ingredient has to be ordered."""
    if not x["order_by"]:
        return "this week"
    return "today" if x["order_by"] == "Today" else f"by {x['order_by']}"


def _more(value):
    return "more" if value >= 0 else "less"


# ── Sales ────────────────────────────────────────────────────────────────────

@_ask("revenue", "How are my sales this week?")
def _(c):
    return (f"Over the last 7 days you averaged {money(c.last7)} a day, {abs(c.growth)}% {_more(c.growth)} than the week "
            f"before ({money(c.before7)} a day). Today you took {money(c.revenue)} from {demo.ORDERS_TODAY} orders.")


@_ask("revenue", "What should I expect next week?")
def _(c):
    total = sum(r["revenue"] for r in c.forecast)
    return (f"We expect about {money(total)} over the next 7 days. {c.busy['day']} should be the busiest at about "
            f"{money(c.busy['revenue'])} and {c.quiet['day']} the quietest at about {money(c.quiet['revenue'])}.")


@_ask("revenue", "Why is Monday so quiet?")
def _(c):
    return c.by_day["Monday"]["why"]


@_ask("revenue", "Which day will be my busiest, and why?")
def _(c):
    return f"{c.busy['day']} should be your busiest day, at about {money(c.busy['revenue'])}. {c.busy['why']}"


@_ask("revenue", "Am I earning more than last week?")
def _(c):
    return (f"{'Yes' if c.growth >= 0 else 'No'}. You averaged {money(c.last7)} a day over the last 7 days against "
            f"{money(c.before7)} the week before, {abs(c.growth)}% {_more(c.growth)}.")


@_ask("revenue", "How much should I expect to take on Saturday?")
def _(c):
    sat = c.by_day["Saturday"]
    return (f"We expect about {money(sat['revenue'])} on Saturday, and a normal Saturday can land anywhere between "
            f"{money(sat['low'])} and {money(sat['high'])}.")


@_ask("revenue", "What is an average order worth?")
def _(c):
    return (f"Today the average order was worth {money(c.revenue // demo.ORDERS_TODAY)}: {money(c.revenue)} from "
            f"{demo.ORDERS_TODAY} orders.")


@_ask("revenue", "How can I get more sales on quiet days?")
def _(c):
    veg = c.dishes["Vegetable bowl"]
    return (f"{c.quiet['day']} is your quietest day coming up: about {money(c.quiet['revenue'])} expected, against "
            f"{money(c.s['overall'])} on a typical day. Prepare a little less that day, and try a vegetable bowl "
            f"special, which keeps {veg['margin_pct']}% of its price.")


# ── Orders ───────────────────────────────────────────────────────────────────

@_ask("orders", "Are any orders running late?")
def _(c):
    late = [r for r in c.area("orders")["rows"] if r[2] == "Delayed"]
    if not demo.DELAYED_ORDERS:
        return "No orders are running late right now."
    named = _list(f"{r[0]} ({r[1].lower()})" for r in late)
    detail = f" {named} has waited longer than usual." if named else ""
    return f"Yes, {demo.DELAYED_ORDERS} orders are running late.{detail} Check the grill queue first."


@_ask("orders", "How many orders are still being prepared?")
def _(c):
    return (f"{demo.OPEN_ORDERS} orders are still being prepared, and {demo.ORDERS_TODAY} have been completed today.")


@_ask("orders", "Which way do guests order most?")
def _(c):
    ranked = sorted(c.channels, key=lambda ch: -ch["value"])
    first, rest = ranked[0], ranked[1:]
    return (f"{first['label']} is the most common: {first['value']} of {demo.ORDERS_TODAY} orders ({c.share(first['value'])}%), "
            f"then {rest[0]['label'].lower()} with {rest[0]['value']} and {rest[1]['label'].lower()} with {rest[1]['value']}.")


@_ask("orders", "What should I do about the late delivery?")
def _(c):
    d = c.area("orders")["decisions"][0]
    return f"{d['next_step']} {d['why']}"


@_ask("orders", "Why do orders get delayed?")
def _(c):
    return (f"Orders queue behind the {demo.BOTTLENECK.lower()}: grill dishes take {demo.GRILL_MIN} minutes while the cold "
            f"station finishes in {demo.COLD_MIN}. That is why {demo.DELAYED_ORDERS} orders are late right now.")


@_ask("orders", "How many orders did we complete today?")
def _(c):
    return (f"{demo.ORDERS_TODAY} orders are complete today, worth {money(c.revenue)}, and {demo.OPEN_ORDERS} more are "
            "still in the kitchen.")


# ── Kitchen ──────────────────────────────────────────────────────────────────

@_ask("kitchen", "Where is the kitchen slowing down?")
def _(c):
    return (f"The {demo.BOTTLENECK.lower()}: {demo.GRILL_MIN} minutes a dish against {demo.COLD_MIN} at the cold station. "
            f"Average preparation across the kitchen is {demo.AVG_PREP_MIN} minutes.")


@_ask("kitchen", "What should I fix before the dinner rush?")
def _(c):
    return (f"Move plating support to the grill. Right now {demo.DELAYED_ORDERS} orders are late and the grill takes "
            f"{demo.GRILL_MIN} minutes, so the cold station ({demo.COLD_MIN} minutes) should help plate grill orders.")


@_ask("kitchen", "How many plates will the kitchen prepare on Saturday?")
def _(c):
    sat = c.by_day["Saturday"]
    change = round((sat["plates"] / c.plates_today - 1) * 100)
    return (f"About {sat['plates']} plates on Saturday, {abs(change)}% {'more' if change >= 0 else 'fewer'} than today's "
            f"{c.plates_today}. We assume the same mix of dishes as today.")


@_ask("kitchen", "Why is the grill so slow?")
def _(c):
    fish = c.dishes["Grilled fish"]
    return (f"{c.alert('kitchen', 'grill')['why']} Grilled fish alone was {fish['units']} of today's {c.plates_today} plates.")


@_ask("kitchen", "How long does a dish take on average?")
def _(c):
    return (f"Preparation averages {demo.AVG_PREP_MIN} minutes from order to plate: {demo.GRILL_MIN} at the grill and "
            f"{demo.COLD_MIN} at the cold station.")


@_ask("kitchen", "Do I need extra hands in the kitchen this week?")
def _(c):
    d = c.area("kitchen")["decisions"][1]
    return f"Yes, for {c.busy['day']}, your busiest day. {d['why']} {d['next_step']}"


# ── Stock ────────────────────────────────────────────────────────────────────

@_ask("stock", "What am I about to run out of?")
def _(c):
    if not c.soon:
        return f"Nothing runs out within {demo.SOON_DAYS:g} days with the sales we expect."
    names = _list(f"{x['name'].lower()} ({x['runs_out_day']})" for x in c.soon)
    return (f"{len(c.soon)} ingredients run out within {demo.SOON_DAYS:g} days with the sales we expect: {names}. "
            f"{c.soon[0]['name']} goes first.")


@_ask("stock", "What should I order today?")
def _(c):
    today = [x for x in c.to_order if x["order_by"] == "Today"]
    if not today:
        return f"Nothing has to be ordered today. The next order is needed by {c.order_list[0][2] if c.order_list else 'later this week'}."
    items = _list(f"{x['name'].lower()} ({qty(x['order_qty'])} {x['unit']})" for x in today)
    return f"Order {items} today. These are the ingredients that run out before a supplier could deliver."


@_ask("stock", "Will I have enough beef for the week?")
def _(c):
    b = c.stock["Beef"]
    if b["order_qty"] > 0:
        return (f"Not without ordering. You have {qty(b['on_hand'])} kg of beef and, with the sales we expect, it lasts about "
                f"{b['runway_days']:g} days and runs out on {b['runs_out_day']}. The week needs about {qty(b['need_7d'])} kg, "
                f"so order about {qty(b['order_qty'])} kg {_when(b)}.")
    return f"Yes. You have {qty(b['on_hand'])} kg of beef and the week needs about {qty(b['need_7d'])} kg."


@_ask("stock", "When will the chicken run out?")
def _(c):
    ch = c.stock["Chicken"]
    if ch["runs_out_day"]:
        tail = f" Order about {qty(ch['order_qty'])} kg {_when(ch)}." if ch["order_qty"] > 0 else ""
        return (f"With the sales we expect, the chicken ({qty(ch['on_hand'])} kg) runs out on {ch['runs_out_day']}, about "
                f"{ch['runway_days']:g} days from now.{tail}")
    return (f"Not within the next 7 days: you have {qty(ch['on_hand'])} kg and use about {qty(ch['daily_use'])} kg a day.")


@_ask("stock", "Which ingredients should I use first?")
def _(c):
    a = c.alert("stock", "veg-expiry")
    return f"{a['title']}. {a['why']} {a['what_to_do']}"


@_ask("stock", "Which dishes are affected if beef runs out?")
def _(c):
    b = c.stock["Beef"]
    pilau = c.dishes["Beef pilau"]
    return (f"Beef is used in {_list(b['used_in'])}. {pilau['name']} sold {pilau['units']} plates today, worth "
            f"{money(pilau['sales'])}, so that is the dish at risk.")


@_ask("stock", "How much food am I at risk of wasting?")
def _(c):
    waste = c.opps["waste"]
    return (f"{waste['quantity']} kg of vegetables are close to their date, worth about {money(waste['value'])}. The kitchen "
            "can still use them in time if it cooks from the oldest batch first.")


@_ask("stock", "Why does stock run out faster at the weekend?")
def _(c):
    sat, sun = c.by_day["Saturday"], c.by_day["Sunday"]
    ratio = sat["revenue"] / c.quiet["revenue"]
    return (f"Because you sell more. We expect about {money(sat['revenue'])} on Saturday and {money(sun['revenue'])} on "
            f"Sunday, against {money(c.quiet['revenue'])} on {c.quiet['day']}. Each ingredient is scaled with the sales, so "
            f"a Saturday uses about {ratio:.1f} times what {c.quiet['day']} does.")


# ── Bookings ─────────────────────────────────────────────────────────────────

@_ask("bookings", "Who is booked tonight?")
def _(c):
    slots = _list(f"{n} at {t} ({state.lower()})" for t, n, state in demo.BOOKING_SLOTS)
    return f"{demo.COVERS_TODAY} guests are expected tonight: {slots}."


@_ask("bookings", "Which bookings still need a reply?")
def _(c):
    return (f"The {c.late_time} booking for {c.late_covers} guests is still awaiting confirmation. Confirm it, or give the "
            f"table to the waitlist ({demo.WAITLIST} tables are waiting).")


@_ask("bookings", "How many guests should I expect on Saturday?")
def _(c):
    sat = c.by_day["Saturday"]
    return (f"About {sat['covers']} guests on Saturday, compared with {demo.COVERS_TODAY} tonight. That assumes the same "
            "number of guests per shilling as today.")


@_ask("bookings", "Should I keep tables free for walk-ins?")
def _(c):
    return (f"Yes, a few. About {demo.NO_SHOW_PCT}% of booked guests do not turn up and {demo.WAITLIST} tables are on the "
            f"waitlist, so keep some free and fill them from the waitlist if the {c.late_time} table is not confirmed.")


@_ask("bookings", "What is my no-show rate?")
def _(c):
    expected = round(demo.COVERS_TODAY * demo.NO_SHOW_PCT / 100)
    return (f"About {demo.NO_SHOW_PCT}% of booked guests do not turn up, based on the sample history. Of tonight's "
            f"{demo.COVERS_TODAY} guests that is roughly {expected}.")


@_ask("bookings", "What should I do about the waitlist?")
def _(c):
    return (f"{demo.WAITLIST} tables are on the waitlist. Confirm the {c.late_time} booking today, and if it does not "
            f"confirm, give that table of {c.late_covers} to the waitlist.")


# ── Team ─────────────────────────────────────────────────────────────────────

@_ask("team", "Is my staff overtime too high?")
def _(c):
    labor = c.opps["labor"]
    return (f"About {demo.OVERTIME_HOURS} hours of overtime today could be avoided, worth about {money(labor['value'])} "
            f"({labor['quantity']} hours at {money(labor['unit_value'])}). Overtime is being paid while a quiet period is "
            "fully staffed.")


@_ask("team", "Is dinner properly staffed?")
def _(c):
    return (f"Dinner looks thin: only {demo.DINNER_PEOPLE} people cover it while lunch has {demo.LUNCH_PEOPLE}, and dinner is "
            f"your busiest time. Moving {demo.OVERTIME_HOURS} hours from the quiet period into dinner would help.")


@_ask("team", "How many people do I need on Saturday?")
def _(c):
    sat = c.by_day["Saturday"]
    return (f"About {sat['people']} people on Saturday, against {demo.SCHEDULED_TODAY} scheduled today "
            f"({sat['people'] - demo.SCHEDULED_TODAY:+d}). That assumes the same sales per person as today "
            f"({money(c.revenue // demo.SCHEDULED_TODAY)}).")


@_ask("team", "How can I cut overtime without hurting service?")
def _(c):
    labor = c.opps["labor"]
    return (f"Move {demo.OVERTIME_HOURS} hours of existing cover from the quiet period into the dinner rush instead of "
            f"paying overtime. That could save about {money(labor['value'])} a day and puts people where service is busiest.")


@_ask("team", "What share of my sales goes on staff?")
def _(c):
    return (f"Staff cost {money(demo.LABOR_KES)} today, which is {c.labor_pct}% of the {money(c.revenue)} you sold.")


@_ask("team", "Which day can I run with fewer people?")
def _(c):
    q = c.quiet
    return (f"{q['day']} is your quietest coming day, so it needs about {q['people']} people against "
            f"{demo.SCHEDULED_TODAY} today. Let it run lean and avoid overtime that day.")


# ── Menu and prices ──────────────────────────────────────────────────────────

@_ask("menu", "Which dish earns me the most?")
def _(c):
    top = max(c.dish_list, key=lambda d: d["contribution"])
    return (f"{top['name']}: it left {money(top['contribution'])} today from {top['units']} plates, keeping "
            f"{money(top['price'] - top['cost'])} a plate after ingredients.")


@_ask("menu", "Should I raise the price of pilau?")
def _(c):
    p, margin = c.dishes["Beef pilau"], c.opps["margin"]
    return (f"It is worth testing. Beef pilau sold {p['units']} plates today and keeps {money(p['price'] - p['cost'])} a plate. "
            f"A {money(margin['unit_value'])} rise is worth {money(margin['value'])} a day if customers still order the "
            "same, which is not guaranteed. Try it in the price calculator before changing anything.")


@_ask("menu", "How can I improve my menu margins?")
def _(c):
    veg, margin = c.dishes["Vegetable bowl"], c.opps["margin"]
    lowest = min(c.dish_list, key=lambda d: d["margin_pct"])
    return (f"Promote the vegetable bowl, which keeps {veg['margin_pct']}% of its price, and test a small pilau price rise "
            f"worth about {money(margin['value'])} a day. {lowest['name']} keeps the smallest share of its price "
            f"({lowest['margin_pct']}%), so watch what its ingredients cost.")


@_ask("menu", "Which dish keeps the least per plate?")
def _(c):
    low = min(c.dish_list, key=lambda d: d["price"] - d["cost"])
    return (f"{low['name']} keeps the least per plate: {money(low['price'] - low['cost'])} ({low['margin_pct']}% of its "
            f"{money(low['price'])} price). It still sold {low['units']} today, so a small amount per plate is not the same "
            "as a poor dish.")


@_ask("menu", "What happens if I raise the pilau price by KES 30?")
def _(c):
    p, margin = c.dishes["Beef pilau"], c.opps["margin"]
    rise = margin["unit_value"]
    break_even = rise * p["units"] / (p["price"] + rise - p["cost"])
    return (f"If customers still order the same {p['units']} plates, you keep {money(rise * p['units'])} more a day. If some "
            f"stop ordering, the gain shrinks, and it is gone once more than {break_even:.1f} plates a day are lost.")


@_ask("menu", "Which dish should I promote?")
def _(c):
    veg = c.dishes["Vegetable bowl"]
    return (f"The vegetable bowl: it keeps {veg['margin_pct']}% of its price and uses the {c.opps['waste']['quantity']} kg of "
            "vegetables that need using first.")


@_ask("menu", "What does each dish cost me to make?")
def _(c):
    costs = _list(f"{d['name']} {money(d['cost'])}" for d in c.dish_list)
    return f"Ingredients per plate: {costs}. Cost to make is ingredients only; staff and running costs come on top."


# ── Money left ───────────────────────────────────────────────────────────────

@_ask("finance", "How much is left after all my costs?")
def _(c):
    return (f"About {money(c.surplus)} of today's {money(c.revenue)} is left after ingredients ({money(c.food)}), staff "
            f"({money(demo.LABOR_KES)}) and running costs ({money(demo.OTHER_COSTS_KES)}). This is a simple day summary, "
            "not net profit.")


@_ask("finance", "Is contribution the same as profit?")
def _(c):
    return (f"No. Contribution is sales minus ingredients, {money(c.contribution)} today. Staff ({money(demo.LABOR_KES)}) and "
            f"running costs ({money(demo.OTHER_COSTS_KES)}) still come out of it, leaving about {money(c.surplus)}.")


@_ask("finance", "Where does my money go each day?")
def _(c):
    return (f"Of today's {money(c.revenue)}: ingredients {money(c.food)} ({c.food_pct}%), staff {money(demo.LABOR_KES)} "
            f"({c.labor_pct}%), running costs {money(demo.OTHER_COSTS_KES)} ({c.other_pct}%), and {money(c.surplus)} "
            f"({c.surplus_pct}%) is left.")


@_ask("finance", "How much of every shilling goes on ingredients?")
def _(c):
    return (f"About {c.food_pct}%: {money(c.food)} of the {money(c.revenue)} you sold. Out of every KES 100 you take, "
            f"roughly KES {round(c.food_pct)} pays for ingredients.")


@_ask("finance", "What should I check before calling today profitable?")
def _(c):
    return (f"Check that the {money(demo.UNMATCHED_KES)} unmatched payment is paired with a sale, and remember that staff and "
            f"running costs come out of contribution. After those, about {money(c.surplus)} is left.")


# ── Costs ────────────────────────────────────────────────────────────────────

@_ask("expenses", "What costs me the most?")
def _(c):
    costs = sorted([("Ingredients", c.food, c.food_pct), ("Staff", demo.LABOR_KES, c.labor_pct),
                    ("Running costs", demo.OTHER_COSTS_KES, c.other_pct)], key=lambda x: -x[1])
    first, second, third = costs
    return (f"{first[0]} cost the most today: {money(first[1])}, or {first[2]}% of sales. Then {second[0].lower()} "
            f"({money(second[1])}) and {third[0].lower()} ({money(third[1])}).")


@_ask("expenses", "How much do I spend on staff?")
def _(c):
    return (f"{money(demo.LABOR_KES)} today, {c.labor_pct}% of sales, with {demo.SCHEDULED_TODAY} people scheduled. About "
            f"{demo.OVERTIME_HOURS} hours of overtime in that could be avoided.")


@_ask("expenses", "How can I lower my costs?")
def _(c):
    waste, labor = c.opps["waste"], c.opps["labor"]
    return (f"Start with ingredients ({c.food_pct}% of sales): use the {waste['quantity']} kg of near-expiry vegetables first, "
            f"worth {money(waste['value'])}. Then move {demo.OVERTIME_HOURS} hours of overtime into the dinner rush, worth "
            f"{money(labor['value'])} a day.")


@_ask("expenses", "Why does cutting waste matter more than cutting staff?")
def _(c):
    waste = c.opps["waste"]
    return (f"Ingredients are the biggest cost ({c.food_pct}% of sales against {c.labor_pct}% for staff), and waste is food "
            f"you paid for and did not sell: the near-expiry vegetables alone are worth {money(waste['value'])}. Cutting "
            f"staff also risks service at dinner, when only {demo.DINNER_PEOPLE} people are covering.")


@_ask("expenses", "What share of my sales goes on running costs?")
def _(c):
    return (f"{c.other_pct}%: {money(demo.OTHER_COSTS_KES)} of the {money(c.revenue)} you sold today, which is the sample "
            "restaurant's utilities and rent.")


# ── Suppliers ────────────────────────────────────────────────────────────────

@_ask("suppliers", "Is any supplier late?")
def _(c):
    a = c.alert("suppliers", "late-meat")
    return f"Yes. {a['title']}. {a['why']}"


@_ask("suppliers", "Who should I call today?")
def _(c):
    beef = c.stock["Beef"]
    return (f"The meat and fish partner: ask for a firm delivery time. {c.po_second[0]} ({money(c.po_second[2])}) is overdue "
            f"and beef runs out on {beef['runs_out_day']}.")


@_ask("suppliers", "Which supplier raised their prices?")
def _(c):
    rows = c.area("suppliers")["rows"]
    row = next(r for r in rows if "price rise" in r[3])
    change = c.metrics("suppliers")["Price change"]
    return (f"The {row[0].lower()} raised prices {change.lstrip('+')}. They supply {row[1].lower()}. Ask another supplier for "
            "a price on rice and oil to compare.")


@_ask("suppliers", "Which supplier provides my beef?")
def _(c):
    supplier = demo.SUPPLIER_OF["Beef"]
    others = [name.lower() for name, who in demo.SUPPLIER_OF.items() if who == supplier and name != "Beef"]
    return (f"The {supplier.lower()}, who also supply {_list(others)}. Their delivery is a day late and you have "
            f"{qty(c.stock['Beef']['on_hand'])} kg of beef.")


@_ask("suppliers", "Why is the late meat delivery a problem?")
def _(c):
    b, pilau = c.stock["Beef"], c.dishes["Beef pilau"]
    return (f"Beef only covers {b['cover_days']:g} days at today's pace, and with the sales we expect it runs out on "
            f"{b['runs_out_day']}. Beef pilau, {pilau['units']} plates a day, depends on it.")


@_ask("suppliers", "Is it worth comparing prices for rice and oil?")
def _(c):
    rice, oil = c.stock["Rice"], c.stock["Cooking oil"]
    change = c.metrics("suppliers")["Price change"]
    return (f"Yes. They come from the {demo.SUPPLIER_OF['Rice'].lower()}, who raised prices {change.lstrip('+')}. Rice lasts "
            f"about {rice['runway_days']:g} days and cooking oil about {oil['runway_days']:g}, so there is time to get a "
            "quote before you order.")


# ── Buying orders ────────────────────────────────────────────────────────────

@_ask("purchasing", "What orders are waiting for me?")
def _(c):
    first, second = c.po_first, c.po_second
    return (f"{len(demo.PURCHASE_ORDERS)} purchase orders worth {money(c.po_total)}: {first[0]} ({money(first[2])}, "
            f"{first[3].lower()}) and {second[0]} ({money(second[2])}, {second[3].lower()}).")


@_ask("purchasing", "What should I order this week?")
def _(c):
    groups = "; ".join(f"{sup}: {what} ({'today' if by == 'Today' else 'by ' + by})" for sup, what, by in c.order_list)
    return f"{len(c.to_order)} ingredients run out within the week. By supplier: {groups}."


@_ask("purchasing", "Which order is overdue?")
def _(c):
    po = c.po_second
    return (f"{po[0]}: {money(po[2])} of meat and fish from the {po[1].lower()}. It should already be here and beef is running "
            "low, so chase the supplier.")


@_ask("purchasing", "Should I approve the dry goods order?")
def _(c):
    rice, oil, po = c.stock["Rice"], c.stock["Cooking oil"], c.po_first
    return (f"Check stock first. {po[0]} is {money(po[2])} of dry goods. Rice lasts about {rice['runway_days']:g} days with the "
            f"sales we expect and cooking oil about {oil['runway_days']:g}, so approve a smaller order if you already have plenty.")


@_ask("purchasing", "Which supplier should I order from first?")
def _(c):
    if not c.order_list:
        return "Nothing needs ordering this week."
    sup, what, by = c.order_list[0]
    return f"The {sup.lower()}: {what}, needed {'today' if by == 'Today' else 'by ' + by}. It is the order that runs out first."


@_ask("purchasing", "When do I need to order the produce?")
def _(c):
    produce = [x for x in c.to_order if x["supplier"] == "Produce partner"]
    if not produce:
        return "Nothing needs ordering from the produce partner this week."
    items = _list(f"{x['name'].lower()} ({qty(x['order_qty'])} {x['unit']}) {_when(x)}" for x in produce)
    return f"From the produce partner: {items}. Suppliers need about a day to deliver."


# ── Cash and M-Pesa ──────────────────────────────────────────────────────────

@_ask("cash-reconciliation", "Does my money match my sales?")
def _(c):
    return (f"Nearly all of it: {money(c.revenue - demo.UNMATCHED_KES)} of {money(c.revenue)} is matched, and "
            f"{money(demo.UNMATCHED_KES)} is not yet.")


@_ask("cash-reconciliation", "Why is KES 1,200 unmatched?")
def _(c):
    return (f"{money(demo.UNMATCHED_KES)} is a payment without a matching sale reference. That is usually a timing or "
            "reference problem, so find the M-Pesa or card reference first.")


@_ask("cash-reconciliation", "What should I do about the unmatched payment?")
def _(c):
    return ("Open the payment reference and pair it with the right sale at close of day. Do not treat it as a loss until "
            "you have checked the reference.")


@_ask("cash-reconciliation", "How much has been settled today?")
def _(c):
    matched = c.revenue - demo.UNMATCHED_KES
    return (f"{money(matched)} of today's {money(c.revenue)} has been matched to a payment ({round(matched / c.revenue * 100)}%), "
            f"with {money(demo.UNMATCHED_KES)} still to settle.")


@_ask("cash-reconciliation", "Is a difference the same as a loss?")
def _(c):
    return (f"No. A difference means a payment and a sale have not been paired yet. Today's {money(demo.UNMATCHED_KES)} gap is "
            f"{round(demo.UNMATCHED_KES / c.revenue * 100, 1)}% of sales and is not proof of loss or theft.")


# ── How guests order ─────────────────────────────────────────────────────────

@_ask("pos", "How are guests ordering?")
def _(c):
    dine, take, delivery = c.channels
    return (f"Of {demo.ORDERS_TODAY} orders, {dine['value']} were dine-in ({c.share(dine['value'])}%), {take['value']} "
            f"takeaway ({c.share(take['value'])}%) and {delivery['value']} delivery ({c.share(delivery['value'])}%).")


@_ask("pos", "How many takeaway orders do I get?")
def _(c):
    take = c.channels[1]
    return f"{take['value']} of today's {demo.ORDERS_TODAY} orders were takeaway, about {c.share(take['value'])}%."


@_ask("pos", "Should I push takeaway or delivery?")
def _(c):
    take, delivery = c.channels[1], c.channels[2]
    first, other = (take, delivery) if take["value"] >= delivery["value"] else (delivery, take)
    tail = f" {c.area('pos')['decisions'][0]['next_step']}" if first is take else ""
    return (f"{first['label']} first: it is {c.share(first['value'])}% of orders against {c.share(other['value'])}% for "
            f"{other['label'].lower()}.{tail}")


@_ask("pos", "Where should I put my staff, based on how guests order?")
def _(c):
    dine, take, delivery = c.channels
    return (f"{dine['value']} of {demo.ORDERS_TODAY} orders ({c.share(dine['value'])}%) are dine-in, so most people belong on "
            f"the floor. Takeaway ({take['value']}) and delivery ({delivery['value']}) share the same kitchen, and the grill "
            f"({demo.GRILL_MIN} minutes) is where they queue, so that is where extra hands help most.")


# ── Marketing ────────────────────────────────────────────────────────────────

@_ask("marketing", "What offer could bring guests back?")
def _(c):
    d = c.area("marketing")["decisions"][0]
    return f"{d['idea']}. {d['why']} {d['next_step']}"


@_ask("marketing", "How many of my guests are returning?")
def _(c):
    new = demo.ORDERS_TODAY - demo.RETURNING_GUESTS
    return (f"{demo.RETURNING_GUESTS} of {demo.ORDERS_TODAY} guests ({c.share(demo.RETURNING_GUESTS)}%) were returning, and "
            f"{new} were new.")


@_ask("marketing", "What special could I run on a quiet day?")
def _(c):
    veg = c.dishes["Vegetable bowl"]
    return (f"On {c.quiet['day']}, your quietest coming day (about {money(c.quiet['revenue'])}), run a vegetable bowl lunch "
            f"special for returning guests. It keeps {veg['margin_pct']}% of its price.")


@_ask("marketing", "How can I use the vegetables that are close to expiry in an offer?")
def _(c):
    veg = c.dishes["Vegetable bowl"]
    waste = c.opps["waste"]
    per_plate = demo.RECIPES["Vegetable bowl"]["Mixed vegetables"]
    return (f"{waste['quantity']} kg of vegetables are near their date. The vegetable bowl uses {qty(per_plate)} kg a plate and "
            f"sold {veg['units']} today, so a lunch offer for returning guests uses up stock worth about "
            f"{money(waste['value'])} that would otherwise be thrown away.")


@_ask("marketing", "How would I know if an offer worked?")
def _(c):
    measure = c.area("marketing")["rows"][0][2]
    return (f"Measure the {measure[0].lower() + measure[1:]}, against what the offer cost you. Nothing is sent from this "
            "demonstration, so no offer has been measured yet.")


# ── Unusual activity ─────────────────────────────────────────────────────────

@_ask("risk", "Is there anything unusual I should check?")
def _(c):
    rows = c.area("risk")["rows"]
    items = "; ".join(f"{r[0].lower()} ({r[1]}): {r[2][0].lower() + r[2][1:]}" for r in rows)
    return f"{len(rows)} things are worth a second look: {items}. Neither is proof of wrongdoing."


@_ask("risk", "Is the unmatched payment theft?")
def _(c):
    confirmed = c.metrics("risk")["Confirmed theft"]
    return (f"Nothing here is proof of theft: confirmed theft is {confirmed}. An unmatched {money(demo.UNMATCHED_KES)} is usually "
            "a timing or reference problem, so check the reference first.")


@_ask("risk", "Why was an order voided after it was cooked?")
def _(c):
    a = c.alert("risk", "void")
    return (f"The demo does not record a reason. {a['why']} Ask the person on shift why it was voided and write it down.")


@_ask("risk", "How do I check without accusing my team?")
def _(c):
    d = c.area("risk")["decisions"][0]
    return f"{d['idea']}. {d['why']} {d['next_step']} A signal is a reason to look, not an accusation."


# ── Alerts ───────────────────────────────────────────────────────────────────

def _alerts(c):
    items = demo.attention_items(c.day)
    urgent = [a for a in items["attention"] if a["level"] == "urgent"]
    return items, urgent


@_ask("notifications", "What needs my attention today?")
def _(c):
    items, urgent = _alerts(c)
    total = len(items["attention"]) + len(items["watching"])
    if not urgent:
        return f"{total} things need your attention, and none is urgent."
    return (f"{total} things need your attention, {len(urgent)} of them urgent. Start with "
            f"{_list(_lc(a['title']) for a in urgent[:3])}.")


@_ask("notifications", "What is urgent right now?")
def _(c):
    _items, urgent = _alerts(c)
    if not urgent:
        return "Nothing is urgent right now."
    return "Urgent now: " + "; ".join(f"{a['title']} ({a['domain']})" for a in urgent) + "."


@_ask("notifications", "What should I deal with first?")
def _(c):
    items, _urgent = _alerts(c)
    first = items["attention"][0]
    return f"{first['title']}. {first['why']} {first['what_to_do']}"


@_ask("notifications", "Are there alerts I can leave for now?")
def _(c):
    items, _urgent = _alerts(c)
    if not items["watching"]:
        return "No. Everything on the list needs attention."
    titles = "; ".join(w["title"] for w in items["watching"])
    return f"Yes, {len(items['watching'])} lower-priority alerts can wait until the urgent ones are done: {titles}."


# ── Ideas ────────────────────────────────────────────────────────────────────

@_ask("intelligence", "Where can I save money?")
def _(c):
    ideas = _list(f"{_lc(o['title'])} ({money(o['value'])})" for o in c.s["opportunities"])
    return (f"{len(c.s['opportunities'])} ideas could be worth {money(c.roi['potential_daily'])} a day if they all work: "
            f"{ideas}. These are chances, not results.")


@_ask("intelligence", "What are the biggest chances I have this week?")
def _(c):
    ranked = sorted(c.s["opportunities"], key=lambda o: -o["value"])
    top = ranked[0]
    rest = _list(f"{_lc(o['title'])} ({money(o['value'])})" for o in ranked[1:])
    return f"The biggest is {_lc(top['title'])}, worth about {money(top['value'])} a day: {top['why']} Then {rest}."


@_ask("intelligence", "What should I focus on today, and why?")
def _(c):
    items = demo.attention_items(c.day)
    first = items["attention"][0]
    top = max(c.s["opportunities"], key=lambda o: o["value"])
    return (f"First deal with {_lc(first['title'])}: {first['why']} Then {_lc(top['title'])}, your biggest idea at "
            f"{money(top['value'])} a day. {top['action']}")


@_ask("intelligence", "Which idea is easiest to start today?")
def _(c):
    waste = c.opps["waste"]
    return (f"{waste['title']}. It uses stock already on your shelf and needs only a decision in your own kitchen: "
            f"{waste['action']} It is worth about {money(waste['value'])} a day.")


@_ask("intelligence", "How much could I gain each day if everything works?")
def _(c):
    sums = " + ".join(money(o["value"]) for o in c.s["opportunities"])
    return (f"{money(c.roi['potential_daily'])} a day ({sums}) if all {len(c.s['opportunities'])} ideas work as assumed. "
            "None of it has been earned yet.")


@_ask("intelligence", "Have I actually earned any of these savings yet?")
def _(c):
    return (f"No. {money(c.roi['realised'])} has been earned so far. The {money(c.roi['potential_daily'])} a day is what the "
            f"{len(c.s['opportunities'])} ideas could be worth, not a result.")


# ── Where the numbers come from ──────────────────────────────────────────────

@_ask("data-trust", "Where do these numbers come from?")
def _(c):
    return (f"From a made-up sample restaurant: {len(c.s['history'])} days of sales, {len(c.s['menu'])} dishes and "
            f"{len(c.s['stock'])} ingredients. Totals are calculated by the system the same way every time.")


@_ask("data-trust", "Can I trust these figures?")
def _(c):
    return ("The sums are calculated the same way every time from the sample data, and every idea shows its working so you can "
            "check it. But the restaurant itself is made up, so treat the figures as an example, not as your results.")


@_ask("data-trust", "Is any real restaurant data being used here?")
def _(c):
    return (f"No. Only {len(c.s['history'])} days of sample sales are used, and no real restaurant data is used or changed.")


@_ask("data-trust", "What would change with my own restaurant connected?")
def _(c):
    return (f"{c.area('data-trust')['how_to_read']} The same sums would then be worked out from your own sales, stock and costs.")


# ── Decisions made ───────────────────────────────────────────────────────────

@_ask("audit", "What decisions have been made?")
def _(c):
    metrics = c.metrics("audit")
    return (f"None yet. {metrics['Suggestions made']} suggestions have been prepared, with {metrics['Changes made']} changes made "
            f"and {metrics['Messages sent']} messages sent.")


@_ask("audit", "Has anything actually been changed?")
def _(c):
    metrics = c.metrics("audit")
    return (f"No. Changes made: {metrics['Changes made']}. Messages sent: {metrics['Messages sent']}. The demo only prepares "
            "suggestions.")


@_ask("audit", "What is waiting for me to decide?")
def _(c):
    rows = c.area("audit")["rows"]
    waiting = [r for r in rows if r[2].lower().startswith("waiting")]
    previews = [r for r in rows if r not in waiting]
    waiting_text = _list(r[0].lower() for r in waiting) or "nothing"
    return (f"Waiting for you: {waiting_text}. The {_list(r[0].lower() for r in previews)} "
            f"{'is a preview' if len(previews) == 1 else 'are previews'} only, so nothing has changed.")


@_ask("audit", "Why does a record of decisions matter?")
def _(c):
    explanation = c.area("audit")["how_to_read"].split(". ")[-1]
    return (f"{explanation} Here it lists {len(c.area('audit')['rows'])} suggestions and "
            f"{c.metrics('audit')['Changes made']} changes made.")


# ── Setup ────────────────────────────────────────────────────────────────────

@_ask("settings", "How is my restaurant set up?")
def _(c):
    return c.area("settings")["headline"]


@_ask("settings", "Which currency and timezone does it use?")
def _(c):
    metrics = c.metrics("settings")
    return f"{metrics['Currency']} (Kenya shillings) and {metrics['Timezone']} time."


@_ask("settings", "Is my restaurant kept separate from others?")
def _(c):
    return f"Yes. {c.area('settings')['action']} Only the Demo owner can see it."


@_ask("settings", "Can this demo change my real records?")
def _(c):
    row = next(r for r in c.area("settings")["rows"] if r[0].startswith("Records changed"))
    return f"No. Records changed by this demo: {row[1].lower()}. Nothing here can be changed or sent."
