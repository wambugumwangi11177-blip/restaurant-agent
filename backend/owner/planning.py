"""Planning uses real recipes and the existing integer-cent combo and kitchen sums."""
from collections import defaultdict
from datetime import timedelta
import models
from owner.kitchen import market_list
from owner.menu_math import combo_summary
from owner.states import kes
from time_utils import EAT_OFFSET, eat_date

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
    return {'state':'as_entered','as_of':ctx.now.isoformat(),'entered_up_to':eat_date(ctx.now).isoformat(),
            'basis':'your planned portions and current saved recipes','dishes':names,'items':market_list(rows),
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
    from ai.cash_reconciliation.intelligence import drawer_tolerance_cents
    from owner.areas import _mpesa
    matches=_mpesa(ctx)
    rows=ctx.db.query(models.CashDrawerCount).filter(models.CashDrawerCount.restaurant_id==ctx.rid,
          models.CashDrawerCount.window_start>=ctx.now-timedelta(days=14)).order_by(models.CashDrawerCount.window_start.desc()).all()
    out=[]
    for c in rows:
        q=ctx.db.query(models.Order).filter(models.Order.restaurant_id==ctx.rid,models.Order.created_at>=c.window_start,models.Order.created_at<c.window_end)
        mpesa=q.filter(models.Order.is_paid.is_(True),models.Order.status!=models.OrderStatus.CANCELLED,models.Order.payment_method==models.PaymentMethod.MPESA).all()
        out.append({'id':c.id,'from':(c.window_start+EAT_OFFSET).isoformat(),'to':(c.window_end+EAT_OFFSET).isoformat(),
                    'expected_kes':kes(c.expected_amount_cents),'counted_kes':kes(c.counted_amount_cents),
                    'gap_kes':kes(c.counted_amount_cents-c.expected_amount_cents),
                    'check':abs(c.counted_amount_cents-c.expected_amount_cents)>drawer_tolerance_cents(c.expected_amount_cents,ctx.settings),
                    'mpesa_sales_kes':kes(sum(o.total for o in mpesa)),
                    'cancelled_sales':q.filter(models.Order.status==models.OrderStatus.CANCELLED).count(),
                    'stock_gap':None})
    return {'state':'as_entered' if rows else 'no_data','as_of':ctx.now.isoformat(),
            'entered_up_to':max((eat_date(c.counted_at).isoformat() for c in rows if c.counted_at),default=None),
            'reason':None if rows else 'No drawer counts recorded in the last 14 days.','shifts':out,
            'mpesa':matches,'note':'Windows are Nairobi time. M-Pesa sales are till totals, not matched payments. Statement exceptions are shown separately. Stock gaps need two zone counts bounding a shift; no shift stock gap is inferred from a weekly total. Overlapping drawer counts are separate checks; do not add their totals.'}
