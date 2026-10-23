"""Owner stock review, using the shared inventory engine at the actual review time."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

import models
from ai.inventory_predictor import _analyze_single_item, _apply_abc_classification
from owner.states import kes
from time_utils import eat_date


def review(ctx):
    from domain.entry_corrections import valid_count_filters, valid_movement_filters
    items = ctx.db.query(models.InventoryItem).filter_by(restaurant_id=ctx.rid).all()
    ids = [i.id for i in items]
    movements = defaultdict(list)
    for row in ctx.db.query(models.StockMovement).filter(
        models.StockMovement.inventory_item_id.in_(ids),
        models.StockMovement.created_at >= ctx.now - timedelta(days=30),
        models.StockMovement.created_at <= ctx.now,
        *valid_movement_filters(ctx.db,ctx.rid),
    ).all():
        movements[row.inventory_item_id].append(row)
    predictions = _apply_abc_classification([
        _analyze_single_item(i, movements[i.id], ctx.now,
                             ctx.now - timedelta(days=30), ctx.now - timedelta(days=7))['prediction']
        for i in items
    ])
    counts = defaultdict(list)
    for row in ctx.db.query(models.StockCount).filter(
        models.StockCount.restaurant_id == ctx.rid,
        models.StockCount.counted_at <= ctx.now,
        *valid_count_filters(ctx.db,ctx.rid),
    ).all():
        counts[row.inventory_item_id].append(row.counted_at)
    predictions_by_id = {p['id']: p for p in predictions}
    rows = []
    total = 0
    for item in items:
        # Classification may reorder rows; resolve explicitly by identifier.
        prediction = predictions_by_id[item.id]
        value = int((Decimal(str(max(item.quantity or 0, 0))) *
                     Decimal(item.cost_per_unit_cents or 0)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        total += value
        interval = {'A': 1, 'B': 7, 'C': 30}[prediction['abc_class']]
        last = max(counts[item.id], default=None)
        due = eat_date(last + timedelta(days=interval)) if last else eat_date(ctx.now)
        rows.append({**prediction, 'value_kes': kes(value),
                     'cost_missing': not item.cost_per_unit_cents,
                     'negative_book_stock': (item.quantity or 0) < 0,
                     'last_count': last.isoformat() if last else None,
                     'count_every_days': interval, 'count_due': due.isoformat(),
                     'count_overdue': due <= eat_date(ctx.now)})
        next_day=max(due,eat_date(ctx.now))
        rows[-1]['count_calendar']=[(next_day+timedelta(days=n)).isoformat()
            for n in range(0,30,interval) if next_day+timedelta(days=n)<eat_date(ctx.now)+timedelta(days=30)]
    purchases = defaultdict(list)
    for po in ctx.db.query(models.PurchaseOrder).filter(
        models.PurchaseOrder.restaurant_id == ctx.rid,
        models.PurchaseOrder.status.in_(['DELIVERED', 'PARTIAL']),
        models.PurchaseOrder.delivered_at >= ctx.now - timedelta(days=90),
        models.PurchaseOrder.delivered_at <= ctx.now,
        models.PurchaseOrder.cost_per_unit > 0,
    ).order_by(models.PurchaseOrder.delivered_at, models.PurchaseOrder.id).all():
        purchases[(po.supplier_id, po.inventory_item_id, po.unit)].append(po)
    prices = []
    by_id = {i.id: i for i in items}
    for (supplier_id, item_id, unit), orders in purchases.items():
        if len(orders) < 2 or item_id not in by_id:
            continue
        first, latest = orders[0], orders[-1]
        supplier = ctx.db.query(models.Supplier).filter_by(id=supplier_id, restaurant_id=ctx.rid).first()
        prices.append({'item': by_id[item_id].item_name, 'supplier': supplier.name if supplier else 'Supplier',
                       'unit': unit, 'first_kes': kes(first.cost_per_unit), 'latest_kes': kes(latest.cost_per_unit),
                       'change_pct': round((latest.cost_per_unit / first.cost_per_unit - 1) * 100, 1),
                       'deliveries': len(orders), 'from': first.delivered_at.isoformat(), 'to': latest.delivered_at.isoformat()})
    latest_entry = max([m.created_at for group in movements.values() for m in group] +
                       [d for group in counts.values() for d in group], default=None)
    return {'state': 'as_entered' if items else 'no_data', 'as_of': ctx.now.isoformat(),
            'entered_up_to': eat_date(latest_entry).isoformat() if latest_entry else None,
            'value_kes': kes(total), 'items': rows, 'supplier_prices': prices,
            'note': 'Book stock at current saved unit costs; missing costs are excluded and negative quantities valued at zero. Waste is recorded waste divided by all recorded stock out over the last 30 days. Supplier comparisons use delivered orders in the same unit over 90 days. Suggested counts: A daily, B weekly, C monthly; never-counted items are due today.'}
