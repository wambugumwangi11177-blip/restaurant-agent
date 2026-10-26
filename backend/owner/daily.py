"""Daily evidence and tasks; existing stock and finance engines remain the accounting source."""
import json
from datetime import timedelta
from sqlalchemy import func,or_
import models
from time_utils import utcnow, eat_date

ZONES = ('store', 'kitchen', 'in_transit')

def zone_event(db, item, zone, delta, kind, actor, key, details=None):
    old=db.query(models.StockZoneEvent).filter_by(entry_key=key).first()
    if old:
        if old.inventory_item_id!=item.id or old.zone!=zone or abs(old.delta-delta)>1e-8:
            raise ValueError('Retry key already used for another movement')
        return old
    row=models.StockZoneEvent(restaurant_id=item.restaurant_id,inventory_item_id=item.id,zone=zone,
        delta=delta,kind=kind,actor_id=actor,entry_key=key,details=json.dumps(details or {}))
    db.add(row)
    return row


def balances(db, item):
    rows=db.query(models.StockZoneEvent.zone,func.sum(models.StockZoneEvent.delta)).filter_by(
        restaurant_id=item.restaurant_id,inventory_item_id=item.id).group_by(models.StockZoneEvent.zone).all()
    values={zone:round(float(delta),6) for zone,delta in rows}
    for zone in ZONES: values.setdefault(zone,0.0)
    values['unallocated']=round(float(item.quantity or 0)-sum(values.values()),6)
    return values


def location_issues(db,rid):
    grouped=db.query(models.StockZoneEvent.inventory_item_id,models.StockZoneEvent.zone,func.sum(models.StockZoneEvent.delta)).filter_by(restaurant_id=rid).group_by(models.StockZoneEvent.inventory_item_id,models.StockZoneEvent.zone).all()
    by_item={}
    for iid,zone,delta in grouped:by_item.setdefault(iid,{})[zone]=float(delta)
    flagged=[]
    for item in db.query(models.InventoryItem).filter_by(restaurant_id=rid).all():
        values=by_item.get(item.id,{})
        if any(n < -1e-6 for n in values.values()) or abs(values.get('in_transit',0))>1e-6 or abs((item.quantity or 0)-sum(values.values())) > 1e-6:
            flagged.append(item.id)
    return flagged


def dispatch(db, transfer):
    source=(transfer.from_location or '').strip().lower();destination=(transfer.to_location or '').strip().lower()
    if source not in ('store','kitchen') or destination not in ('store','kitchen'):return
    item=db.query(models.InventoryItem).filter_by(id=transfer.inventory_item_id,restaurant_id=transfer.restaurant_id).one()
    key=f'transfer:{transfer.id}'
    zone_event(db,item,source,-transfer.quantity,'dispatch',transfer.initiated_by_user_id,key+':store',{'transfer_id':transfer.id})
    zone_event(db,item,'in_transit',transfer.quantity,'dispatch',transfer.initiated_by_user_id,key+':transit',{'transfer_id':transfer.id})


def arrive(db, transfer):
    # Legacy handovers did not have independent zone balances. Do not manufacture their location history.
    if not db.query(models.StockZoneEvent).filter_by(entry_key=f'transfer:{transfer.id}:store').first(): return
    item=db.query(models.InventoryItem).filter_by(id=transfer.inventory_item_id,restaurant_id=transfer.restaurant_id).one()
    zone_event(db,item,'in_transit',-transfer.confirmed_quantity,'receipt',transfer.confirmed_by_user_id,f'transfer:{transfer.id}:arrival-out')
    zone_event(db,item,transfer.to_location.strip().lower(),transfer.confirmed_quantity,'receipt',transfer.confirmed_by_user_id,f'transfer:{transfer.id}:arrival-in')


def reopen(db,rid,day,reason):
    row=db.query(models.DailyShiftClose).filter_by(restaurant_id=rid,day=day).with_for_update().first()
    if row and row.status in ('closed','closed_with_exceptions','ready_for_review'):
        history=json.loads(row.history)
        history.append({'at':utcnow().isoformat(),'action':'reopened','reason':reason})
        row.history=json.dumps(history);row.status='open';row.closed_at=None;row.version+=1


def day_checks(db,rid,day,settings):
    from owner.money.pnl import nairobi_utc_range
    lo,hi=nairobi_utc_range(day,day)
    counts=db.query(models.CashDrawerCount).filter(models.CashDrawerCount.restaurant_id==rid,
        models.CashDrawerCount.window_start>=lo,models.CashDrawerCount.window_end<=hi).all()
    cash=sum(c.counted_amount_cents-c.expected_amount_cents for c in counts)
    transfers=db.query(models.StockTransfer).filter(models.StockTransfer.restaurant_id==rid,
        models.StockTransfer.status.in_([models.StockTransferStatus.REQUESTED,models.StockTransferStatus.PENDING,models.StockTransferStatus.DISPUTED]),
        or_(models.StockTransfer.initiated_at<hi,models.StockTransfer.initiated_at.is_(None))).count()
    from domain.entry_corrections import valid_count_filters
    whole_counts={r.inventory_item_id for r in db.query(models.StockCount).filter(models.StockCount.restaurant_id==rid,models.StockCount.counted_at>=lo,models.StockCount.counted_at<hi,*valid_count_filters(db,rid)).all()}
    zone_counts=set()
    for r in db.query(models.StockZoneEvent).filter(models.StockZoneEvent.restaurant_id==rid,models.StockZoneEvent.kind=='count').all():
        captured=json.loads(r.details).get('captured_at')
        at=__import__('datetime').datetime.fromisoformat(captured.replace('Z','+00:00')).replace(tzinfo=None) if captured else r.created_at
        if lo<=at<hi:zone_counts.add((r.inventory_item_id,r.zone))
    # Initial daily close requires a physical record for each tracked item; a whole-item count or both zone counts qualify.
    required={r.id for r in db.query(models.InventoryItem).filter_by(restaurant_id=rid).all()}
    covered=whole_counts|{iid for iid in required if (iid,'store') in zone_counts and (iid,'kitchen') in zone_counts}
    stock_done=bool(required) and required<=covered
    physical=len(required&covered)
    paid_at=func.coalesce(models.Order.completed_at,models.Order.created_at)
    paid=db.query(models.Order).filter(models.Order.restaurant_id==rid,models.Order.is_paid.is_(True),
        paid_at>=lo,paid_at<hi,models.Order.status!=models.OrderStatus.CANCELLED).count()
    from owner.mpesa_match import Sale, Payment, match
    sales=db.query(models.Order).filter(models.Order.restaurant_id==rid,paid_at>=lo,
        paid_at<hi,models.Order.is_paid.is_(True),models.Order.status!=models.OrderStatus.CANCELLED,
        models.Order.payment_method==models.PaymentMethod.MPESA).all()
    lines=db.query(models.MpesaStatementLine).filter_by(restaurant_id=rid).filter(models.MpesaStatementLine.paid_in_cents>0).all()
    day_lines=[l for l in lines if lo<=l.completed_at<hi]
    matched=match([Sale(o.id,o.completed_at or o.created_at,o.total,o.mpesa_receipt) for o in sales],
        [Payment(l.id,l.completed_at,l.paid_in_cents,l.receipt) for l in day_lines],settings.mpesa_match_minutes)
    statement_complete=bool(lines and min(l.completed_at for l in lines)<=lo and max(l.completed_at for l in lines)>=hi)
    mpesa_ok=(not sales and not day_lines) or (statement_complete and not matched.sales_without_payment and not matched.payments_without_sale and not matched.different_amounts)
    overlapping=any(a.id!=b.id and a.window_start<b.window_end and b.window_start<a.window_end for a in counts for b in counts)
    zone_issues=location_issues(db,rid)
    checks=[{'key':'locations','label':'Location balances reconciled','done':not zone_issues,'detail':f'{len(zone_issues)} items have unallocated stock, negative location records or goods still in transit'},
        {'key':'cash','label':'Blind cash count recorded','done':bool(counts),'detail':f'{len(counts)} submitted counts'},
        {'key':'stock','label':'Physical stock count recorded','done':stock_done,'detail':f'{physical} of {len(required)} tracked items counted; both locations or a whole-item count required'},
        {'key':'handovers','label':'Handovers resolved','done':transfers==0,'detail':f'{transfers} pending or disputed'},
        {'key':'cash_difference','label':'Cash difference within your tolerance','done':bool(counts) and not overlapping and all(abs(c.counted_amount_cents-c.expected_amount_cents)<=max(settings.cash_tolerance_cents,abs(c.expected_amount_cents)*settings.cash_tolerance_pct/100) for c in counts),'detail':'Overlapping drawer windows need review' if overlapping else f'KES {cash/100:,.2f} signed difference'},
        {'key':'mpesa','label':'M-Pesa statement reviewed','done':mpesa_ok,'detail':'No M-Pesa sales or statement payments in this shift' if not sales and not day_lines else 'Review statement coverage and exceptions before closing'}]
    return checks,{'paid_orders':paid,'cash_difference_kes':cash/100}
