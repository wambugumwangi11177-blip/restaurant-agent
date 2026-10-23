"""Evidence-backed menu review and learning from owner-approved price changes."""
from collections import defaultdict
from datetime import timedelta
from math import log
from statistics import median

import models
from owner.states import kes
from time_utils import EAT_OFFSET, eat_date


def price_results(db, rid, now):
    changes = db.query(models.PricingRecommendation).filter(
        models.PricingRecommendation.restaurant_id == rid,
        models.PricingRecommendation.status == 'APPROVED',
        models.PricingRecommendation.actioned_at.isnot(None),
        models.PricingRecommendation.actioned_at <= now,
    ).order_by(models.PricingRecommendation.actioned_at).all()
    out = []
    for change in changes:
        at = change.actioned_at
        dish = db.query(models.MenuItem).filter_by(id=change.menu_item_id, restaurant_id=rid).first()
        if dish is None:
            continue
        row = {'id': change.id, 'dish_id': dish.id, 'dish': dish.name, 'changed_at': at.isoformat(),
               'old_kes': kes(change.current_price), 'new_kes': kes(change.suggested_price),
               'state': 'learning', 'reason': 'Needs 14 complete days after the change.',
               'elasticity': None, 'revenue_change_kes': None}
        end = at + timedelta(days=14)
        if end > now:
            out.append(row)
            continue
        trading=[o.created_at for o in db.query(models.Order).filter(
            models.Order.restaurant_id==rid,models.Order.is_paid.is_(True),
            models.Order.status!=models.OrderStatus.CANCELLED,
            models.Order.created_at>=at-timedelta(days=14),models.Order.created_at<end).all()]
        if len({eat_date(t) for t in trading if t<at})<7 or len({eat_date(t) for t in trading if t>=at})<7:
            row['reason']='Both windows need at least seven recorded trading days before reporting a revenue result. Missing feed data is not counted as zero demand.'
            out.append(row)
            continue
        other = any(c.id != change.id and c.menu_item_id == dish.id and
                    at-timedelta(days=14) < c.actioned_at < end for c in changes)
        lines = db.query(models.OrderItem, models.Order).join(models.Order).filter(
            models.Order.restaurant_id == rid, models.OrderItem.menu_item_id == dish.id,
            models.Order.is_paid.is_(True), models.Order.status != models.OrderStatus.CANCELLED,
            models.Order.created_at >= at-timedelta(days=14), models.Order.created_at < end).all()
        before = [l for l, o in lines if o.created_at < at]
        after = [l for l, o in lines if o.created_at >= at]
        bq, aq = sum(l.quantity for l in before), sum(l.quantity for l in after)
        br = sum(l.quantity * (l.unit_price or 0) for l in before)
        ar = sum(l.quantity * (l.unit_price or 0) for l in after)
        row.update(before_portions=bq, after_portions=aq, before_revenue_kes=kes(br),
                   after_revenue_kes=kes(ar), revenue_change_kes=kes(ar-br), state='as_entered',
                   reason='Observed 14-day revenue change; other factors may explain it. Not proven savings.')
        price_ratio = change.suggested_price / max(change.current_price, 1)
        verified = (all(l.unit_price == change.current_price for l in before) and
                    all(l.unit_price == change.suggested_price for l in after))
        before_days={eat_date(o.created_at) for l,o in lines if o.created_at<at}
        after_days={eat_date(o.created_at) for l,o in lines if o.created_at>=at}
        if not other and verified and bq >= 30 and aq >= 30 and len(before_days)>=7 and len(after_days)>=7 and abs(price_ratio-1) >= .03:
            measured = log(aq / bq) / log(price_ratio)
            if -3 <= measured <= -.05:
                row['elasticity'] = round(measured, 4)
                row['reason'] += ' Measured demand response is used in future price simulations.'
        if row['elasticity'] is None:
            row['reason'] += ' Demand learning needs isolated changes, matching recorded prices, 30 portions on at least seven trading days in each window and a negative response between -3 and -0.05.'
        out.append(row)
    return out


def learned_sensitivity(db, rid, item_id, now):
    values = [r['elasticity'] for r in price_results(db, rid, now)
              if r['dish_id'] == item_id and r['elasticity'] is not None]
    return median(values) if values else None


def menu_review(ctx):
    dishes = ctx.db.query(models.MenuItem).filter_by(restaurant_id=ctx.rid).all()
    totals = defaultdict(lambda: [0, 0])
    for line, order in ctx.db.query(models.OrderItem, models.Order).join(models.Order).filter(
        models.Order.restaurant_id == ctx.rid, models.Order.is_paid.is_(True),
        models.Order.status != models.OrderStatus.CANCELLED,
        models.Order.created_at >= ctx.now-timedelta(days=30), models.Order.created_at <= ctx.now).all():
        totals[line.menu_item_id][0] += line.quantity
        totals[line.menu_item_id][1] += line.quantity * (line.unit_price or 0)
    revenue = sum(v[1] for v in totals.values())
    rows, cumulative = [], 0
    for d in sorted(dishes, key=lambda d: (-totals[d.id][1], d.id)):
        qty, sales = totals[d.id]
        tail = revenue > 0 and cumulative >= revenue * .95
        rows.append({'id': d.id, 'name': d.name, 'category': d.category or 'Other', 'price_kes': kes(d.price),
                     'is_available': d.is_available,
                     'portions': qty, 'sales_kes': kes(sales), 'tail': tail,
                     'kept_kes': kes(sales-qty*d.cost_price) if d.cost_price else None,
                     'cumulative_pct': round((cumulative+sales)/revenue*100, 1) if revenue else None})
        cumulative += sales
    tail_ids = {r['id'] for r in rows if r['tail']}
    links = ctx.db.query(models.MenuIngredient).filter(models.MenuIngredient.menu_item_id.in_([d.id for d in dishes])).all()
    removable = {l.inventory_item_id for l in links if l.menu_item_id in tail_ids} - {
        l.inventory_item_id for l in links if l.menu_item_id not in tail_ids}
    ladder = sorted([r for r in rows if r['price_kes'] > 0], key=lambda r: (r['price_kes'], r['id']))
    gaps = sorted([{'from_kes': a['price_kes'], 'to_kes': b['price_kes'],
                    'gap_kes': round(b['price_kes']-a['price_kes'], 2)}
                   for a, b in zip(ladder, ladder[1:]) if b['price_kes'] > a['price_kes']],
                  key=lambda g: -g['gap_kes'])[:5]
    from owner.areas import _menu
    matrix = _menu(ctx).get('matrix', [])
    stars = [m for m in matrix if m.get('classification') == 'Star']
    puzzles = [m for m in matrix if m.get('classification') == 'Puzzle']
    by_id = {d.id: d for d in dishes}
    from owner.menu_math import target_price_cents
    combos = []
    for star in stars[:3]:
        for puzzle in puzzles[:3]:
            a, b = by_id.get(star['id']), by_id.get(puzzle['id'])
            if a and b and a.cost_price and b.cost_price:
                minimum = target_price_cents(a.cost_price+b.cost_price, ctx.settings.margin_floor_pct, ctx.settings.price_step_cents)
                if minimum < a.price+b.price:
                    combos.append({'ids': [a.id, b.id], 'dishes': [a.name, b.name], 'minimum_kes': kes(minimum),
                                   'regular_kes': kes(a.price+b.price), 'floor_pct': ctx.settings.margin_floor_pct})
    return {**ctx.order_state(needs_days=30), 'items': rows, 'ladder': ladder, 'gaps': gaps,
            'tail_ingredients': len(removable), 'combos': combos,
            'results': price_results(ctx.db, ctx.rid, ctx.now),
            'note': 'Last 30 days of paid sales. Tail starts after 95% of revenue; review availability and guest needs before trimming. Kept amounts use current saved dish costs. Price gaps describe your menu, not proven unmet demand. Combo prices are minimums at your margin floor, not automatic offers.'}


def branch_review(ctx):
    from domain.entry_corrections import valid_count_filters
    from owner.answer_compare import _branch
    from owner.states import OwnerContext
    from routers.deps import list_restaurants_for_tenant
    rows=[]
    for restaurant in list_restaurants_for_tenant(ctx.db,ctx.user):
        c=OwnerContext(ctx.db,ctx.user,restaurant);c.now=ctx.now
        row=_branch(c,restaurant)
        counts=ctx.db.query(models.CashDrawerCount).filter(models.CashDrawerCount.restaurant_id==restaurant.id,
            models.CashDrawerCount.window_start>=ctx.now-timedelta(days=30),models.CashDrawerCount.window_end<=ctx.now).all()
        overlap=any(a.id!=b.id and a.window_start<b.window_end and b.window_start<a.window_end for a in counts for b in counts)
        row['cash_gap_kes']=kes(sum(c.counted_amount_cents-c.expected_amount_cents for c in counts)) if counts and not overlap else None
        row['cash_note']='Overlapping checks: review separately' if overlap else f'{len(counts)} recorded drawer checks'
        stock=ctx.db.query(models.StockCount,models.InventoryItem).join(models.InventoryItem).filter(
            models.StockCount.restaurant_id==restaurant.id,models.InventoryItem.restaurant_id==restaurant.id,
            models.StockCount.counted_at>=ctx.now-timedelta(days=30),models.StockCount.counted_at<=ctx.now,
            *valid_count_filters(ctx.db,restaurant.id)).all()
        row['stock_gaps_kes']=kes(sum(round(max(s.expected_quantity-s.counted_quantity,0)*(i.cost_per_unit_cents or 0)) for s,i in stock)) if stock else None
        from owner.areas import _profit
        gaps=_profit(c).get('till_price_gap',[])
        row['below_menu_estimate_kes_month']=kes(sum(g['estimated_monthly_leak'] for g in gaps))
        row['stock_checks']=len(stock)
        rows.append(row)
    return {'state':'as_entered' if rows else 'no_data','branches':rows,
            'note':'Sales, food and wages use each branch’s shared 30-day engine. Cash is the signed difference from non-overlapping checks in the last 30 days; overlapping checks are not added. Stock is the recorded positive count discrepancies at current costs, not a proven loss total. Below-menu pricing is an estimate against today’s menu, not an audited discount ledger.'}
