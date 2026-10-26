"""Planning uses real recipes and the existing integer-cent combo and kitchen sums."""
from collections import defaultdict
from datetime import timedelta
import models
from owner.kitchen import market_list
from owner.menu_math import combo_summary
from owner.states import kes
from time_utils import EAT_OFFSET, eat_date


def forecast_portions(ctx, target):
    """Same-weekday observed portions; unobserved trading days never become zero sales."""
    from math import ceil
    from statistics import mean
    from datetime import datetime, time
    today = eat_date(ctx.now)
    if not today <= target <= today + timedelta(days=7):
        raise ValueError('Choose today or a day in the next week')
    days = [today-timedelta(days=n) for n in range(1, 36)
            if (today-timedelta(days=n)).weekday() == target.weekday()][:4]
    history = defaultdict(lambda: defaultdict(int))
    for line, order in ctx.db.query(models.OrderItem, models.Order).join(models.Order).filter(
        models.Order.restaurant_id == ctx.rid, models.Order.is_paid.is_(True),
        models.Order.status != models.OrderStatus.CANCELLED,
        models.Order.created_at >= datetime.combine(min(days), time())-EAT_OFFSET,
        models.Order.created_at < datetime.combine(today, time())-EAT_OFFSET).all():
        day = eat_date(order.created_at)
        if day in days:
            history[day][line.menu_item_id] += line.quantity
    dishes = ctx.db.query(models.MenuItem).filter_by(restaurant_id=ctx.rid, is_available=True).all()
    recipe_ids = {l.menu_item_id for l in ctx.db.query(models.MenuIngredient).filter(
        models.MenuIngredient.menu_item_id.in_([d.id for d in dishes])).all()}
    rows = []
    for dish in dishes:
        samples = [values.get(dish.id, 0) for values in history.values()]
        if samples and sum(samples):
            rows.append({'menu_item_id': dish.id, 'dish': dish.name, 'portions': ceil(mean(samples)),
                         'low': min(samples), 'high': max(samples), 'has_recipe': dish.id in recipe_ids})
    return {**ctx.order_state(needs_days=28), 'date': target.isoformat(), 'dishes': rows,
            'observed_days': sorted(d.isoformat() for d in history),
            'note': 'Mean portions across up to four recorded matching weekdays, rounded up; range is historical min–max, not a confidence interval. Missing trading days are omitted. Review events, bookings and stock-outs before accepting. Dishes without recipes cannot enter the raw prep plan.'}

def prepare(ctx, portions):
    needs=defaultdict(float)
    names=[]
    for choice in portions:
        dish=ctx.db.query(models.MenuItem).filter_by(id=choice.menu_item_id,restaurant_id=ctx.rid).first()
        if dish is None:
            raise ValueError('Dish not found')
        recipe=ctx.db.query(models.MenuIngredient).filter_by(menu_item_id=dish.id).all()
        if not recipe:
            raise ValueError(f'{dish.name}: add a recipe before planning')
        for line in recipe:
            item=ctx.db.query(models.InventoryItem).filter_by(id=line.inventory_item_id,restaurant_id=ctx.rid).first()
            if item is None:
                raise ValueError('Recipe contains a stock item outside this restaurant')
            needs[item.id]+=line.raw_quantity_per_serving*choice.portions
        names.append({'dish':dish.name,'portions':choice.portions})
    rows=[]
    for iid,need in sorted(needs.items()):
        i=ctx.db.query(models.InventoryItem).filter_by(id=iid,restaurant_id=ctx.rid).one()
        rows.append(dict(item=i.item_name,unit=i.unit,need=round(need,4),buffer=i.par_level or 0,on_hand=max(i.quantity or 0,0)))
    calculated = market_list(rows)
    for row, iid in zip(calculated, sorted(needs)):
        item = ctx.db.query(models.InventoryItem).filter_by(id=iid, restaurant_id=ctx.rid).one()
        supplier = ctx.db.query(models.Supplier).filter_by(id=item.default_supplier_id, restaurant_id=ctx.rid).first()
        row.update(inventory_item_id=iid, supplier_id=supplier.id if supplier else None,
                   supplier=supplier.name if supplier else 'Choose supplier',
                   cost_per_unit_cents=item.cost_per_unit_cents or 0)
    return {'state':'as_entered','as_of':ctx.now.isoformat(),'entered_up_to':eat_date(ctx.now).isoformat(),
            'basis':'your planned portions and current saved recipes','dishes':names,'items':calculated,
            'note':'Your planned portions, recipe yields and full-shelf levels; not a sales forecast or a purchase order. Negative book stock is treated as zero on hand.'}

def combo(ctx, ids, price):
    dishes=[ctx.db.query(models.MenuItem).filter_by(id=i,restaurant_id=ctx.rid).first() for i in ids]
    if any(d is None for d in dishes):
        raise ValueError('Dish not found')
    if any(d.cost_price is None or d.cost_price<=0 for d in dishes):
        raise ValueError('Enter the cost of each dish before checking a combo')
    result=combo_summary([d.price for d in dishes],price,[d.cost_price for d in dishes],ctx.settings.margin_floor_pct)
    return {'state':'as_entered','as_of':ctx.now.isoformat(),'entered_up_to':eat_date(ctx.now).isoformat(),
            'basis':'your combo price and current saved dish costs',
            'dishes':[d.name for d in dishes],**{k.replace('_cents','_kes'):kes(v) if k.endswith('_cents') else v for k,v in result.items()},
            'floor_pct':ctx.settings.margin_floor_pct,'note':'Uses current dish costs. No prices are changed and demand is not estimated.'}

def shifts(ctx):
    from domain.entry_corrections import valid_count_filters
    from ai.cash_reconciliation.intelligence import drawer_tolerance_cents
    from owner.areas import _mpesa
    matches=_mpesa(ctx)
    stock_catalog=ctx.db.query(models.InventoryItem).filter_by(restaurant_id=ctx.rid).all()
    count_history=defaultdict(list)
    for count in ctx.db.query(models.StockCount).filter(models.StockCount.restaurant_id==ctx.rid,
        models.StockCount.counted_at>=ctx.now-timedelta(days=14),models.StockCount.counted_at<=ctx.now,
        *valid_count_filters(ctx.db,ctx.rid)).order_by(models.StockCount.counted_at).all():
        count_history[count.inventory_item_id].append(count)
    from owner.mpesa_match import match, Sale, Payment
    from sqlalchemy import func
    lines = ctx.db.query(models.MpesaStatementLine).filter_by(restaurant_id=ctx.rid).filter(models.MpesaStatementLine.paid_in_cents > 0).all()
    paid_at = func.coalesce(models.Order.completed_at, models.Order.created_at)
    all_sales = ctx.db.query(models.Order).filter(models.Order.restaurant_id == ctx.rid,
        models.Order.is_paid.is_(True), models.Order.payment_method == models.PaymentMethod.MPESA,
        models.Order.status != models.OrderStatus.CANCELLED).all()
    lo = min((l.completed_at for l in lines), default=None)
    hi = max((l.completed_at for l in lines), default=None)
    covered_from = (lo+EAT_OFFSET).replace(hour=0, minute=0, second=0, microsecond=0)-EAT_OFFSET if lo else None
    sale_rows = [Sale(o.id, o.completed_at or o.created_at, o.total, o.mpesa_receipt)
                 for o in all_sales if covered_from and covered_from <= (o.completed_at or o.created_at) <= hi+timedelta(minutes=ctx.settings.mpesa_match_minutes)]
    matched = match(sale_rows, [Payment(l.id, l.completed_at, l.paid_in_cents, l.receipt) for l in lines], ctx.settings.mpesa_match_minutes)
    matched_ids = {i for m in matched.matched for i in m.sales}
    unmatched_ids = {s.id for s in matched.sales_without_payment}
    different_ids = {s.id for s, p in matched.different_amounts}
    rows=ctx.db.query(models.CashDrawerCount).filter(models.CashDrawerCount.restaurant_id==ctx.rid,
          models.CashDrawerCount.window_start>=ctx.now-timedelta(days=14)).order_by(models.CashDrawerCount.window_start.desc()).all()
    out=[]
    for c in rows:
        q=ctx.db.query(models.Order).filter(models.Order.restaurant_id==ctx.rid,models.Order.created_at>=c.window_start,models.Order.created_at<c.window_end)
        mpesa=ctx.db.query(models.Order).filter(models.Order.restaurant_id==ctx.rid,paid_at>=c.window_start,paid_at<c.window_end,
            models.Order.is_paid.is_(True),models.Order.status!=models.OrderStatus.CANCELLED,models.Order.payment_method==models.PaymentMethod.MPESA).all()
        stock_rows = []
        for item in stock_catalog:
            counts = [count for count in count_history[item.id] if c.window_start<=count.counted_at<=c.window_end]
            if len(counts)==2 and counts[0].counted_at<=c.window_start+timedelta(minutes=15) and counts[-1].counted_at>=c.window_end-timedelta(minutes=15):
                close=counts[-1]
                stock_rows.append({'item':item.item_name,'from':counts[0].counted_at.isoformat(),'to':close.counted_at.isoformat(),
                    'missing_quantity':round(close.expected_quantity-close.counted_quantity,4), 'unit':item.unit,
                    'gap_kes':kes(round((close.expected_quantity-close.counted_quantity)*item.cost_per_unit_cents)) if item.cost_per_unit_cents else None})
        stock_known = [r['gap_kes'] for r in stock_rows if r['gap_kes'] is not None]
        out.append({'id':c.id,'from':(c.window_start+EAT_OFFSET).isoformat(),'to':(c.window_end+EAT_OFFSET).isoformat(),
                    'expected_kes':kes(c.expected_amount_cents),'counted_kes':kes(c.counted_amount_cents),
                    'gap_kes':kes(c.counted_amount_cents-c.expected_amount_cents),
                    'check':abs(c.counted_amount_cents-c.expected_amount_cents)>drawer_tolerance_cents(c.expected_amount_cents,ctx.settings),
                    'mpesa_sales_kes':kes(sum(o.total for o in mpesa)),
                    'cancelled_sales':q.filter(models.Order.status==models.OrderStatus.CANCELLED).count(),
                    'mpesa_matched_kes':kes(sum(o.total for o in mpesa if o.id in matched_ids)),
                    'mpesa_unmatched_kes':kes(sum(o.total for o in mpesa if o.id in unmatched_ids or o.id in different_ids)),
                    'mpesa_outside_statement_kes':kes(sum(o.total for o in mpesa if o.id not in matched_ids|unmatched_ids|different_ids)),
                    'mpesa_statement_complete':bool(covered_from and covered_from<=c.window_start and hi>=c.window_end),
                    'stock_gap':round(sum(stock_known),2) if stock_known else None, 'stock_items':stock_rows})
    return {'state':'as_entered' if rows else 'no_data','as_of':ctx.now.isoformat(),
            'entered_up_to':max((eat_date(c.counted_at).isoformat() for c in rows if c.counted_at),default=None),
            'reason':None if rows else 'No drawer counts recorded in the last 14 days.','shifts':out,
            'mpesa':matches,'note':'Nairobi time. M-Pesa uses receipt/exact/grouped/split statement matching, attributed by payment time; outside-statement sales are not missing payments. Stock covers only items with exactly two physical counts inside the shift, within 15 minutes of its boundaries; the actual count interval is shown. Other items remain unknown. Cancelled sales are orders opened in the shift. Overlapping drawer checks must not be added.'}


def price_impact(ctx, menu_item_id, new_price_cents):
    from sqlalchemy import func
    from owner.areas import month_pnl
    from owner.money.pnl import nairobi_utc_range
    from datetime import date
    dish=ctx.db.query(models.MenuItem).filter_by(id=menu_item_id,restaurant_id=ctx.rid).first()
    if dish is None:
        raise LookupError("Dish not found in this branch")
    pnl=month_pnl(ctx)
    start,end=nairobi_utc_range(date.fromisoformat(pnl['period']['start']),date.fromisoformat(pnl['period']['end']))
    end=min(end,ctx.now)
    portions=int(ctx.db.query(func.coalesce(func.sum(models.OrderItem.quantity),0)).join(models.Order,models.Order.id==models.OrderItem.order_id).filter(
        models.Order.restaurant_id==ctx.rid,models.OrderItem.menu_item_id==dish.id,models.Order.is_paid.is_(True),
        models.Order.status!=models.OrderStatus.CANCELLED,models.Order.created_at>=start,models.Order.created_at<end).scalar())
    delta_cents=(new_price_cents-dish.price)*portions
    delta=delta_cents/100
    before={r['key']:r['kes'] for r in pnl['lines']}
    after={k:round(v+(delta if k in {'sales','left_after_ingredients','kept'} else 0),2) for k,v in before.items()}
    if after['sales'] <= 0:
        raise ValueError('This price difference exceeds the recorded sales baseline. Choose a smaller change.')
    def pct(key,value,sales):
        if not sales:return None
        return round((abs(value) if key in {'ingredients','wages','other_costs'} else value)/sales*100,2)
    rows=[{'key':r['key'],'label':r['label'],'before_kes':r['kes'],'after_kes':after[r['key']],
           'before_pct':pct(r['key'],r['kes'],before['sales']),
           'after_pct':pct(r['key'],after[r['key']],after['sales']),
           'change_kes':round(after[r['key']]-r['kes'],2)} for r in pnl['lines']]
    return {'dish':dish.name,'portions':portions,'current_price_kes':dish.price/100,'new_price_kes':new_price_cents/100,
            'period':pnl['period'],'rows':rows,'extra_sales_kes':delta,'complete':pnl['complete'],
            'missing_costs':pnl.get('missing_costs',[]),'notes':pnl.get('notes',[]),
            'assumption':'Illustration using this month’s recorded portions at the proposed price difference from today’s menu. Same portions, ingredient costs, wages and other costs. Demand and commission changes are not modelled. No price is saved. Use Ask LEVIII for a demand-response simulation.'}


def price_simulation(ctx, menu_item_id: int, new_price_cents: int) -> dict:
    """Owner-facing adapter over the same demand engine used by Ask; read-only, tenant scoped."""
    from ai.simulation.engine import simulate_price_change
    item = ctx.db.query(models.MenuItem).filter_by(id=menu_item_id, restaurant_id=ctx.rid).first()
    if item is None:
        raise LookupError('Dish not found in this restaurant')
    result = simulate_price_change(ctx.db, ctx.rid, menu_item_id, new_price_cents, ctx.settings)
    if not result.get('available'):
        raise ValueError(result.get('error', 'Could not model this price'))
    before, after = result['baseline'], result['projected']
    known_cost = bool(item.cost_price and item.cost_price > 0)
    return {
        'state': 'assumption' if before['daily_qty'] > 0 else 'no_data',
        'dish': item.name, 'current_price_kes': kes(item.price), 'proposed_price_kes': kes(new_price_cents),
        'rows': [
            {'key': 'portions', 'label': 'Portions per 30 days', 'unit': 'portions', 'before': before['monthly_qty'], 'after': after['monthly_qty']},
            {'key': 'sales', 'label': 'Dish sales per 30 days', 'unit': 'kes', 'before': kes(before['monthly_revenue_cents']), 'after': kes(after['monthly_revenue_cents'])},
            {'key': 'contribution', 'label': 'Left after this dish’s ingredients', 'unit': 'kes', 'before': kes(before['monthly_profit_cents']) if known_cost else None, 'after': kes(after['monthly_profit_cents']) if known_cost else None},
            {'key': 'margin', 'label': 'Share left after ingredients', 'unit': 'percent', 'before': before['margin_pct'] if known_cost else None, 'after': after['margin_pct'] if known_cost else None},
        ],
        'demand_change_pct': result['deltas']['sales_pct'],
        'elasticity': result['elasticity_used'], 'sensitivity_source': result['sensitivity_source'],
        'confidence_pct': result['confidence_pct'],
        'notes': [
            'Assumption, not a promise: projected demand uses the shared price-response model and recorded sales history.',
            'A 30-day dish contribution comparison. Wages, rent, other operating costs and delivery commissions are excluded; this is not restaurant net profit.',
            'No menu price is saved. Check the fixed-portions P&L comparison separately.',
        ] + (['No recorded demand for this dish in the baseline; record sales before relying on a projection.'] if before['daily_qty'] == 0 else [])
          + ([] if known_cost else ['Ingredient cost is missing; contribution and margin cannot be calculated.']),
    }
