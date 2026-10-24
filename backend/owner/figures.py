"""The guide pictures that need their own series.

Each figure is a small payload with a state. An empty restaurant gets no_data
and a reason; nothing here calls a language model or invents a number.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from math import log

from sqlalchemy import func

import models
from owner.states import OwnerContext, block, kes, no_data, unavailable
from time_utils import EAT_OFFSET, eat_date, trading_window

KEYS = (
    "three_way", "short_count", "stock_history", "shilling", "price_tree",
    "elasticity", "price_ladder", "pareto", "abc_calendar", "why_tree",
    "alert_pyramid", "door_cards",
)


def _empty(reason: str, **fields) -> dict:
    return no_data(reason, **fields)


def _as_entered(ctx: OwnerContext, when=None, **fields) -> dict:
    """A counted or typed figure. `entered_up_to` is the Nairobi date, same as every other as-entered block."""
    moment = when or ctx.now
    return block("as_entered", as_of=moment, entered_up_to=eat_date(moment).isoformat(), **fields)


def three_way(ctx: OwnerContext) -> dict:
    return ctx.cached("figure.three_way", lambda: _three_way(ctx))


def _three_way(ctx: OwnerContext) -> dict:
    """Cash counted, M-Pesa on the statement, and card sales against a settlement we do not have yet."""
    row = ctx.db.query(models.CashDrawerCount).filter(
        models.CashDrawerCount.restaurant_id == ctx.rid,
        models.CashDrawerCount.window_start >= ctx.now - timedelta(days=14),
    ).order_by(models.CashDrawerCount.window_start.desc()).first()
    window = "latest cash count in the last 14 days"
    if row is None:
        return _empty("A cash count, an M-Pesa statement and card sales will meet here for each shift.", window=window, legs=[])
    card_cents = ctx.db.query(func.coalesce(func.sum(models.Order.total), 0)).filter(
        models.Order.restaurant_id == ctx.rid, models.Order.is_paid.is_(True),
        models.Order.status != models.OrderStatus.CANCELLED,
        models.Order.payment_method == models.PaymentMethod.CARD,
        models.Order.created_at >= row.window_start, models.Order.created_at < row.window_end,
    ).scalar() or 0
    gap = row.counted_amount_cents - row.expected_amount_cents
    from ai.cash_reconciliation.intelligence import drawer_tolerance_cents
    cash_look = abs(gap) > drawer_tolerance_cents(row.expected_amount_cents, ctx.settings)
    legs = [
        {"key": "cash", "label": "Cash", "left_kes": kes(row.counted_amount_cents), "right_kes": kes(row.expected_amount_cents),
         "left_label": "Counted", "right_label": "Till", "look": cash_look},
        {"key": "mpesa", "label": "M-Pesa", "left_kes": None, "right_kes": None,
         "left_label": "On the statement", "right_label": "Recorded sales", "look": False,
         "note": "The statement match is on the M-Pesa check."},
        {"key": "card", "label": "Card", "left_kes": kes(int(card_cents)), "right_kes": None,
         "left_label": "Card sales in this count", "right_label": "Settlement not recorded", "look": False},
    ]
    return _as_entered(ctx, row.counted_at or ctx.now, window=window, legs=legs,
                       reason=None if int(card_cents) or row.expected_amount_cents else "This count has no card sales, and no card settlement is recorded.")


def short_count(ctx: OwnerContext) -> dict:
    return ctx.cached("figure.short_count", lambda: _short_count(ctx))


def _short_count(ctx: OwnerContext) -> dict:
    row = ctx.db.query(models.CashDrawerCount).filter(
        models.CashDrawerCount.restaurant_id == ctx.rid,
        models.CashDrawerCount.window_start >= ctx.now - timedelta(days=14),
    ).order_by(models.CashDrawerCount.window_start.desc()).first()
    window = "latest cash count in the last 14 days"
    if row is None:
        return _empty("A short count draws here once a drawer is counted.", window=window, bars=[])
    gap = row.counted_amount_cents - row.expected_amount_cents
    cancelled = ctx.db.query(func.count(models.Order.id)).filter(
        models.Order.restaurant_id == ctx.rid, models.Order.status == models.OrderStatus.CANCELLED,
        models.Order.created_at >= row.window_start, models.Order.created_at < row.window_end,
    ).scalar() or 0
    short = gap < 0
    trick = None
    if short and not cancelled:
        trick = "Cash taken and the sale left off, or the sale rung and the cash kept."
    elif short:
        trick = "The drawer is short and sales were cancelled in the same count. Check both."
    return _as_entered(ctx, row.counted_at or ctx.now, window=window,
                       expected_kes=kes(row.expected_amount_cents), counted_kes=kes(row.counted_amount_cents),
                 gap_kes=kes(gap), short=short, cancelled=int(cancelled), trick=trick,
                 bars=[{"key": "expected", "label": "Till", "kes": kes(row.expected_amount_cents)},
                       {"key": "counted", "label": "Counted", "kes": kes(row.counted_amount_cents)}],
                 reason=None if short else "This count is not short.")


def stock_history(ctx: OwnerContext) -> dict:
    return ctx.cached("figure.stock_history", lambda: _stock_history(ctx))


def _stock_history(ctx: OwnerContext) -> dict:
    item = ctx.db.query(models.InventoryItem).filter(models.InventoryItem.restaurant_id == ctx.rid).order_by(models.InventoryItem.id).first()
    window = "last 14 days"
    if item is None:
        return _empty("Stock history draws once an item is on the shelf.", window=window, points=[])
    movements = ctx.db.query(models.StockMovement).filter(
        models.StockMovement.inventory_item_id == item.id,
        models.StockMovement.created_at >= ctx.now - timedelta(days=14),
        models.StockMovement.created_at <= ctx.now,
    ).order_by(models.StockMovement.created_at).all()
    # Walk backwards from the quantity on the shelf so each day is a level, not a guess.
    on_hand = float(item.quantity or 0)
    by_day: dict = {}
    today = eat_date(ctx.now)
    cursor = on_hand
    day_delta: dict = defaultdict(float)
    for move in movements:
        signed = float(move.quantity or 0)
        if move.movement_type == models.StockMovementType.OUT:
            signed = -abs(signed)
        day_delta[eat_date(move.created_at)] += signed
    for back in range(14):
        day = today - timedelta(days=back)
        by_day[day] = round(cursor, 4)
        cursor -= day_delta.get(day, 0)
    points = [{"date": day.isoformat(), "on_hand": by_day[day]} for day in sorted(by_day)]
    reorder = float(item.low_stock_threshold) if item.low_stock_threshold is not None else None
    par = float(item.par_level) if item.par_level else None
    reason = None if movements else "No stock movements in the last 14 days, so the line is only what is on the shelf now."
    if not movements:
        return {**_empty(reason, window=window, item=item.item_name, unit=item.unit, reorder=reorder, par=par, points=points)}
    return _as_entered(ctx, window=window, item=item.item_name, unit=item.unit,
                       reorder=reorder, par=par, points=points, reason=reason)


def shilling(ctx: OwnerContext) -> dict:
    """One real paid order, then the statement line when the receipt is on file."""
    start, end, _day = trading_window("today", ctx.now)
    order = ctx.db.query(models.Order).filter(
        models.Order.restaurant_id == ctx.rid, models.Order.is_paid.is_(True),
        models.Order.status != models.OrderStatus.CANCELLED,
        models.Order.created_at >= ctx.now - timedelta(days=14), models.Order.created_at <= ctx.now,
    ).order_by(models.Order.created_at.desc()).first()
    if order is None:
        return _empty("Follow a shilling once a paid order is recorded.", window="last 14 days", steps=[])
    method = order.payment_method.value if order.payment_method else "unknown"
    steps = [{"step": "Order", "detail": f"Order {order.id} · KES {kes(order.total)} · {method}", "kes": kes(order.total)}]
    if method == "mpesa" and order.mpesa_receipt:
        line = ctx.db.query(models.MpesaStatementLine).filter_by(restaurant_id=ctx.rid, receipt=order.mpesa_receipt).first()
        if line is None:
            steps.append({"step": "Statement", "detail": f"Receipt {order.mpesa_receipt} is not on a statement yet.", "kes": None})
        else:
            steps.append({"step": "Statement", "detail": f"Receipt {line.receipt} · KES {kes(line.paid_in_cents)} paid in.", "kes": kes(line.paid_in_cents)})
        steps.append({"step": "Receipt", "detail": order.mpesa_receipt, "kes": kes(order.total)})
    elif method == "mpesa":
        steps.append({"step": "Statement", "detail": "This M-Pesa sale has no receipt number, so it cannot be found on a statement.", "kes": None})
        steps.append({"step": "Receipt", "detail": "No receipt recorded.", "kes": None})
    else:
        steps.append({"step": "Statement", "detail": "Only an M-Pesa sale is checked against the statement.", "kes": None})
        steps.append({"step": "Receipt", "detail": "No M-Pesa receipt on this order.", "kes": None})
    in_today = start <= order.created_at < end
    return block("live", as_of=order.created_at, window="last 14 days", order_id=order.id,
                 service_day="today" if in_today else eat_date(order.created_at).isoformat(), steps=steps, reason=None)


def price_tree(ctx: OwnerContext) -> dict:
    dish = ctx.db.query(models.MenuItem).filter(
        models.MenuItem.restaurant_id == ctx.rid, models.MenuItem.cost_price > 0, models.MenuItem.price > 0,
    ).order_by(models.MenuItem.id).first()
    if dish is None:
        return _empty("A price decision needs a dish with a cost and a menu price.", nodes=[])
    from owner.menu_math import target_price_cents
    suggested = target_price_cents(dish.cost_price, ctx.settings.margin_floor_pct, ctx.settings.price_step_cents)
    nodes = [
        {"title": "Cost", "detail": f"{dish.name} costs KES {kes(dish.cost_price)}."},
        {"title": "Floor", "detail": f"Keep at least {ctx.settings.margin_floor_pct:g}%."},
        {"title": "Suggested", "detail": f"KES {kes(suggested)} is the lowest step that keeps that share."},
        {"title": "You decide", "detail": "Nothing changes on the menu until you approve it."},
    ]
    return _as_entered(ctx, dish=dish.name, nodes=nodes, reason=None)


def elasticity(ctx: OwnerContext) -> dict:
    change = ctx.db.query(models.PricingRecommendation).filter(
        models.PricingRecommendation.restaurant_id == ctx.rid,
        models.PricingRecommendation.status == "APPROVED",
        models.PricingRecommendation.actioned_at.isnot(None),
        models.PricingRecommendation.actioned_at <= ctx.now,
    ).order_by(models.PricingRecommendation.actioned_at.desc()).first()
    if change is None:
        return _empty("Approve a price change to see how portions moved.", points=[])
    dish = ctx.db.query(models.MenuItem).filter_by(id=change.menu_item_id, restaurant_id=ctx.rid).first()
    name = dish.name if dish else "Dish"
    old_kes, new_kes = kes(change.current_price), kes(change.suggested_price)
    at = change.actioned_at
    if at + timedelta(days=14) > ctx.now:
        return block("learning", as_of=ctx.now, day=(ctx.now - at).days + 1, of=14,
                     reason="Needs 14 complete days after the change.", dish=name,
                     points=[{"price_kes": old_kes, "portions": None}, {"price_kes": new_kes, "portions": None}])
    def portions(lo, hi) -> int:
        return int(ctx.db.query(func.coalesce(func.sum(models.OrderItem.quantity), 0)).join(models.Order).filter(
            models.Order.restaurant_id == ctx.rid, models.OrderItem.menu_item_id == change.menu_item_id,
            models.Order.is_paid.is_(True), models.Order.status != models.OrderStatus.CANCELLED,
            models.Order.created_at >= lo, models.Order.created_at < hi,
        ).scalar() or 0)
    before, after = portions(at - timedelta(days=14), at), portions(at, at + timedelta(days=14))
    slope = None
    if before >= 30 and after >= 30 and change.current_price and change.suggested_price and change.suggested_price != change.current_price:
        try:
            measured = log(after / before) / log(change.suggested_price / change.current_price)
        except ValueError:
            measured = None
        if measured is not None and -3 <= measured <= -0.05:
            slope = round(measured, 4)
    return _as_entered(ctx, dish=name, elasticity=slope, window="14 days before and after the change",
                 points=[{"price_kes": old_kes, "portions": before}, {"price_kes": new_kes, "portions": after}],
                 reason=None if slope is not None else "Portions are shown. A slope is only drawn when both windows have at least 30 portions and the response is negative.")


def price_ladder(ctx: OwnerContext) -> dict:
    dishes = ctx.db.query(models.MenuItem).filter(
        models.MenuItem.restaurant_id == ctx.rid, models.MenuItem.price > 0,
    ).order_by(models.MenuItem.price, models.MenuItem.id).limit(24).all()
    if not dishes:
        return _empty("The price ladder fills in once dishes have a menu price.", rungs=[])
    rungs = [{"dish": d.name, "price_kes": kes(d.price)} for d in dishes]
    return _as_entered(ctx, window="menu prices now", rungs=rungs, reason=None)


def pareto(ctx: OwnerContext) -> dict:
    since = ctx.now - timedelta(days=30)
    rows = ctx.db.query(
        models.MenuItem.name,
        func.coalesce(func.sum(models.OrderItem.quantity * models.OrderItem.unit_price), 0),
    ).join(models.OrderItem, models.OrderItem.menu_item_id == models.MenuItem.id).join(
        models.Order, models.Order.id == models.OrderItem.order_id,
    ).filter(
        models.Order.restaurant_id == ctx.rid, models.Order.is_paid.is_(True),
        models.Order.status != models.OrderStatus.CANCELLED,
        models.Order.created_at >= since, models.Order.created_at <= ctx.now,
    ).group_by(models.MenuItem.id, models.MenuItem.name).order_by(
        func.sum(models.OrderItem.quantity * models.OrderItem.unit_price).desc(),
    ).limit(12).all()
    total = sum(int(cents or 0) for _name, cents in rows)
    if total <= 0:
        return _empty("The cumulative line needs paid sales in the last 30 days.", window="last 30 days", points=[])
    running = 0
    points = []
    for name, cents in rows:
        running += int(cents or 0)
        points.append({"dish": name, "sales_kes": kes(int(cents or 0)), "cumulative_pct": round(running / total * 100, 1)})
    return block("live", as_of=ctx.now, window="last 30 days", points=points, reason=None)


def abc_calendar(ctx: OwnerContext) -> dict:
    items = ctx.db.query(models.InventoryItem).filter(models.InventoryItem.restaurant_id == ctx.rid).all()
    if not items:
        return _empty("The count calendar fills in once stock items are recorded.", window="next 14 days", cells=[])
    ranked = sorted(items, key=lambda i: -((i.quantity or 0) * (i.cost_per_unit_cents or 0)))
    values = [max(i.quantity or 0, 0) * (i.cost_per_unit_cents or 0) for i in ranked]
    total = sum(values) or 1
    running = 0
    classes = []
    for item, value in zip(ranked, values):
        share = running / total
        running += value
        classes.append((item, "A" if share < 0.8 else "B" if share < 0.95 else "C"))
    last = dict(ctx.db.query(models.StockCount.inventory_item_id, func.max(models.StockCount.counted_at)).filter(
        models.StockCount.restaurant_id == ctx.rid).group_by(models.StockCount.inventory_item_id).all())
    today = eat_date(ctx.now)
    cells = []
    for item, abc in classes[:8]:
        interval = {"A": 1, "B": 7, "C": 30}[abc]
        counted = last.get(item.id)
        due = eat_date(counted + timedelta(days=interval)) if counted else today
        start = max(due, today)
        days = [(start + timedelta(days=n)).isoformat() for n in range(0, 14, interval) if start + timedelta(days=n) < today + timedelta(days=14)]
        cells.append({"item": item.item_name, "abc": abc, "days": days})
    return _as_entered(ctx, window="next 14 days", cells=cells,
                       reason=None if any(c["days"] for c in cells) else "No count falls in the next 14 days.")


def why_tree(ctx: OwnerContext) -> dict:
    start, end, day = trading_window("yesterday", ctx.now)
    sales = ctx.db.query(func.coalesce(func.sum(models.Order.total), 0), func.count(models.Order.id)).filter(
        models.Order.restaurant_id == ctx.rid, models.Order.is_paid.is_(True),
        models.Order.status != models.OrderStatus.CANCELLED,
        models.Order.created_at >= start, models.Order.created_at < end,
    ).one()
    if not ctx.db.query(models.Order.id).filter(models.Order.restaurant_id == ctx.rid).first():
        return _empty("A why-tree needs a day of sales to explain.", drivers=[])
    cancelled = int(ctx.db.query(func.count(models.Order.id)).filter(
        models.Order.restaurant_id == ctx.rid, models.Order.status == models.OrderStatus.CANCELLED,
        models.Order.created_at >= start, models.Order.created_at < end,
    ).scalar() or 0)
    drivers = [
        {"key": "holiday", "label": "Holiday", "found": False, "detail": "No holiday calendar is checked on this picture."},
        {"key": "stock", "label": "Stock ran out", "found": False, "detail": "A dish that stopped selling is on the store panel, not guessed here."},
        {"key": "staff", "label": "Fewer staff", "found": False, "detail": "Staff hours for that day are on the staff panel."},
        {"key": "cancelled", "label": "Cancelled sales", "found": cancelled >= 3, "detail": f"{cancelled} cancelled in that service day."},
    ]
    return block("live", as_of=ctx.now, window="yesterday", day=day.isoformat(), sales_kes=kes(int(sales[0] or 0)),
                 orders=int(sales[1] or 0), drivers=drivers, reason=None)


def alert_pyramid(ctx: OwnerContext) -> dict:
    from ai.alert_levels import NOW, TODAY, WEEK, level_for
    since = ctx.now - timedelta(days=7)
    rows = ctx.db.query(models.Notification.event_type, func.count(models.Notification.id)).filter(
        models.Notification.user_id == ctx.user.id, models.Notification.created_at >= since,
    ).group_by(models.Notification.event_type).all()
    levels = {NOW: 0, TODAY: 0, WEEK: 0}
    for event_type, count in rows:
        levels[level_for(event_type)] += int(count)
    total = sum(levels.values())
    payload = {"window": "last 7 days", "levels": [
        {"key": NOW, "label": "Now", "count": levels[NOW]},
        {"key": TODAY, "label": "Today", "count": levels[TODAY]},
        {"key": WEEK, "label": "This week", "count": levels[WEEK]},
    ]}
    if total == 0:
        return _empty("No alerts in the last 7 days.", **payload)
    return block("live", as_of=ctx.now, reason=None, **payload)


def door_cards(ctx: OwnerContext, areas: dict) -> dict:
    cash = (areas.get("cash") or {}).get("blocks") or {}
    store = (areas.get("store") or {}).get("blocks") or {}
    permits = (areas.get("permits") or {}).get("blocks") or {}
    money = (areas.get("money") or {}).get("blocks") or {}
    shifts = cash.get("shifts") or {}
    short = sum(1 for s in shifts.get("shifts") or [] if s.get("check"))
    mpesa = cash.get("mpesa") or {}
    mpesa_gap = 0
    if isinstance(mpesa.get("sales_without_payment"), dict):
        mpesa_gap = int(mpesa["sales_without_payment"].get("count") or 0)
    missing = [i for i in (store.get("missing") or {}).get("items") or [] if i.get("check")]
    licences = [i for i in (permits.get("licences") or {}).get("items") or [] if i.get("status") in ("expired", "expiring")]
    bills = [b for b in (money.get("bills") or {}).get("upcoming") or [] if b.get("short")]
    doors = [
        {"key": "till", "title": "The till", "window": "last 14 days",
         "signal": "look" if short else "clear" if shifts.get("shifts") else "no_data",
         "detail": f"{short} cash counts to look at." if short else "No short count in the last 14 days." if shifts.get("shifts") else "No cash count in the last 14 days."},
        {"key": "mpesa", "title": "M-Pesa", "window": "the days the statement covers",
         "signal": "look" if mpesa_gap else "clear" if mpesa.get("checked") else "no_data",
         "detail": f"{mpesa_gap} sales with no payment on the statement." if mpesa_gap else "No unmatched M-Pesa sale." if mpesa.get("checked") else "No statement uploaded."},
        {"key": "store", "title": "The store", "window": "last 7 days",
         "signal": "look" if missing else "clear" if (store.get("missing") or {}).get("items") is not None else "no_data",
         "detail": f"{len(missing)} items used beyond what sales explain." if missing else "Nothing flagged in the last 7 days." if (store.get("missing") or {}).get("items") is not None else "No stock movements recorded."},
        {"key": "calendar", "title": "The calendar", "window": "licences and the next bills",
         "signal": "look" if licences or bills else "clear" if (permits.get("licences") or {}).get("items") or (money.get("bills") or {}).get("upcoming") is not None else "no_data",
         "detail": f"{len(licences)} licences close to expiry, {len(bills)} bills the forecast cannot cover." if licences or bills else "No licence or bill is pressing."},
    ]
    if all(d["signal"] == "no_data" for d in doors):
        return _empty("Each door fills in once that part of the restaurant has records.", doors=doors)
    return block("live", as_of=ctx.now, doors=doors, reason=None)


def compose(ctx: OwnerContext, areas: dict | None = None) -> dict:
    areas = areas or {}
    builders = {
        "three_way": lambda: three_way(ctx),
        "short_count": lambda: short_count(ctx),
        "stock_history": lambda: stock_history(ctx),
        "shilling": lambda: shilling(ctx),
        "price_tree": lambda: price_tree(ctx),
        "elasticity": lambda: elasticity(ctx),
        "price_ladder": lambda: price_ladder(ctx),
        "pareto": lambda: pareto(ctx),
        "abc_calendar": lambda: abc_calendar(ctx),
        "why_tree": lambda: why_tree(ctx),
        "alert_pyramid": lambda: alert_pyramid(ctx),
        "door_cards": lambda: door_cards(ctx, areas),
    }
    return {key: ctx.safe(f"figure.{key}", builders[key]) for key in KEYS}
