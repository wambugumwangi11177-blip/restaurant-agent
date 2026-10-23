"""Health tiles promised in Eleven's guide. Read the same source blocks; never substitute a different metric."""
from datetime import timedelta
from owner.states import block, iso
from owner.money.pnl import compute_pnl, period_range
from owner.money.view import owner_pnl
from time_utils import eat_date


def compose(ctx, areas):
    tiles = []
    def tile(key, number, unit, label, word, status, state, source_meta=None, **extra):
        source_meta = source_meta or {}
        meta = {k:source_meta[k] for k in ('entered_up_to','day','of','age_days','source','reason') if k in source_meta}
        if state in ('no_data','unavailable'):
            meta['reason'] = source_meta.get('reason') or 'No recorded data for this measure yet.'
        tiles.append(dict(area=key, title=areas[key]['title'], number=number, unit=unit, label=label,
                          word=word, status=status, state=state, as_of=source_meta.get('as_of') or iso(ctx.now), **meta, **extra))
    today = eat_date(ctx.now)
    start, end = period_range('week', today)
    pnl = ctx.safe('health.week_pnl', lambda: owner_pnl(
        compute_pnl(ctx.db, ctx.rid, start, end, ctx.settings, today=today),
        'week', ctx.settings, as_of=ctx.now, sales_state=ctx.order_state()['state']))
    kept = next((x['kes'] for x in pnl.get('lines', []) if x['key'] == 'kept'), None) if pnl['state'] != 'no_data' else None
    tile('money', kept, 'KES', 'What you kept this week (as entered)',
         'Costs not covered' if kept is not None and kept < 0 else 'Costs covered' if kept is not None else 'No costs yet',
         'unknown' if kept is None else 'bad' if kept < 0 else 'watch' if not pnl.get('complete') else 'good',
         pnl['state'], source_meta=pnl)
    # Like-for-like finished Nairobi days rather than a full week against a partial one.
    from routers.overview import _summarize
    from owner.money.pnl import nairobi_utc_range
    lo, hi = nairobi_utc_range(today - timedelta(days=7), today - timedelta(days=1))
    sales = _summarize(ctx.db, ctx.rid, lo, hi)['revenue']
    previous = _summarize(ctx.db, ctx.rid, lo-timedelta(days=7), hi-timedelta(days=7))['revenue']
    change = round((sales-previous)/previous*100, 1) if previous else None
    sales_source = ctx.order_state(needs_days=14)
    if change is None and sales_source['state'] == 'live':
        sales_source = {'state':'no_data','reason':'No sales in the prior comparison period; a percentage cannot be calculated.'}
    tile('sales_dishes', change, '%', 'Sales vs the previous 7 complete days', 'Down' if change is not None and change < 0 else 'Up' if change is not None else 'Learning',
         'bad' if change is not None and change < -ctx.settings.sales_drop_flag_pct else 'good' if change is not None else 'unknown',
         sales_source['state'], source_meta=sales_source)
    missing = areas['store']['blocks'].get('missing', {'state':'unavailable'})
    items = missing.get('items')
    value = round(sum(abs(i['missing_value']) for i in items if i['check']), 2) if items is not None else None
    tile('store', value, 'KES', 'Stock gaps to check, last 7 days', 'Check stock' if value else 'No gaps flagged' if value == 0 else 'Count stock',
         'bad' if value else 'good' if value == 0 else 'unknown', missing['state'], source_meta=missing)
    cash = areas['cash']['blocks']
    shifts, mpesa = cash.get('shifts', {'state':'unavailable'}), cash.get('mpesa', {'state':'unavailable'})
    gaps = shifts.get('shifts')
    cash_gap = sum(abs(s['gap']) for s in gaps if s['check']) if gaps is not None else None
    mpesa_gap = sum(mpesa.get(k, {}).get('kes', 0) for k in ('sales_without_payment','payments_without_sale'))
    mpesa_gap += sum(abs(pair['sale_kes']-pair['payment_kes']) for pair in mpesa.get('different_amounts', []))
    total = round((cash_gap or 0) + mpesa_gap, 2) if gaps is not None or 'checked' in mpesa else None
    incomplete = gaps is None or 'checked' not in mpesa
    cash_source = shifts if gaps is not None else mpesa
    tile('cash', total, 'KES', 'Cash gaps (14 days) + statement gaps',
         'Check money (incomplete)' if total and incomplete else 'Check money' if total else 'Check incomplete' if incomplete else 'Balanced',
         'bad' if total else 'watch' if incomplete else 'good', cash_source['state'], source_meta=cash_source)
    staff = areas['staff']['summary']
    tile('staff', staff['number'], staff['unit'], staff['label'], staff['word'], staff['status'], areas['staff']['blocks'].get('wages', {'state':'unavailable'})['state'], source_meta=areas['staff']['blocks'].get('wages', {}))
    licences = areas['permits']['blocks'].get('licences', {'state':'unavailable'})
    nearest = min(licences.get('items', []), key=lambda x:x['days_left'], default=None)
    days = nearest['days_left'] if nearest else None
    tile('permits', days, 'days', f"Next expiry: {nearest['name']}" if nearest else 'Next licence expiry',
         'Expired' if days is not None and days < 0 else 'Expires soon' if days is not None and days < ctx.settings.licence_warning_days else 'Fine' if nearest else 'Add licences',
         'bad' if days is not None and days < ctx.settings.licence_warning_days else 'good' if nearest else 'unknown', licences['state'], source_meta=licences)
    return block('live' if any(t['number'] is not None for t in tiles) else 'no_data', as_of=ctx.now, tiles=tiles, reason=None if any(t['number'] is not None for t in tiles) else 'The tiles fill in as sales and costs are recorded.')
