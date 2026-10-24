"""Read-only Home findings from specialist modules omitted by decision ranking.

Amounts are source estimates, not recoveries. Safety signals invite review,
never accuse a member of staff or execute a source-system change.
"""
import logging
import models

logger = logging.getLogger(__name__)


def collect(db, rid):
    cards, states = [], {}

    def add(domain, title, why, action, impact='', entity='', impact_cents_month=None, kind=None):
        cards.append(dict(domain=domain, title=title, why=why, what_to_do=action,
                          impact=impact, status='open', entity=str(entity), impact_cents_month=impact_cents_month, kind=kind))

    def profit():
        from ai.profit.intelligence import get_profit_intelligence
        data = get_profit_intelligence(db, rid)
        from ai.creative import clean_dish_name
        for leak in data.get('profit_leaks', [])[:4]:
            add('Profit', f"Review margin on {clean_dish_name(leak['item_name'])}",
                f"It keeps {leak['current_margin_pct']:g}% of its price, under the lowest share you said you accept. "
                'The figure is what the gap to your floor costs in a month at the prices and sales recorded; it is not verified recoverable profit.',
                leak['action'], f"About KSh {leak['monthly_leak_cents'] / 100:,.0f} a month to your floor",
                leak.get('item_id', leak['item_name']), impact_cents_month=leak['monthly_leak_cents'] or None, kind='loss')
        return bool(data.get('summary', {}).get('total_orders_30d'))

    def kitchen():
        from ai.kds_intelligence import get_kds_intelligence
        data = get_kds_intelligence(db, rid)
        for row in data.get('bottlenecks', [])[:4]:
            add('Kitchen', f"Review preparation at {row.get('station', 'recorded station')}",
                'A bottleneck was detected in recorded preparation times; this does not establish the live queue.',
                'Check recorded tickets and station staffing before changing the kitchen setup.',
                entity=row.get('station', ''))
        return bool(data.get('station_performance'))

    def reservations():
        from ai.reservation_optimizer import get_reservation_insights
        data = get_reservation_insights(db, rid)
        analysis = data.get('no_show_analysis', {})
        if analysis.get('no_shows'):
            period = analysis.get('period') or 'all recorded reservations, not one day'
            add('Bookings', f"Review {analysis['no_shows']} recorded no-shows ({period})",
                f"{analysis['no_show_rate']}% of {analysis['total_reservations']} recorded reservations. {period}. Not today's arrivals.",
                'Review booking confirmations and cancellation records before changing deposit policies.')
        return bool(analysis.get('total_reservations'))

    def cash_fraud():
        from ai.cash_reconciliation.intelligence import compute_reconciliation_report
        from ai.fraud.detection import compute_fraud_report
        cash = compute_reconciliation_report(db, rid)
        fraud = compute_fraud_report(db, rid)
        for row in cash.drawer_variances:
            if row.flagged:
                add('Cash review', f'Review drawer count {row.count_id}',
                    'The counted amount differs from the recorded expectation beyond tolerance. This is not proof of theft.',
                    'Reconcile the count, float and receipts with the shift owner.',
                    f'Difference KSh {row.variance_cents / 100:,.2f}', row.count_id)
        if fraud.payment_mismatches:
            # D1: ONE summary card for the rule, however many orders it matches — never a card per order.
            n = len(fraud.payment_mismatches)
            total = sum(row.total_cents for row in fraud.payment_mismatches)
            add('Payment review', f"Check M-Pesa payment evidence for {n} order{'s' if n != 1 else ''}",
                'Marked paid through an M-Pesa request from this system, but no receipt is recorded. A missing receipt does not prove non-payment.',
                'Match these orders to settlement records before taking action.',
                f'KSh {total / 100:,.0f} across these orders', 'payment_review')
        for label, rows in [('void activity', fraud.void_spikes), ('refund activity', fraud.refund_velocity), ('off-hours activity', fraud.off_hours)]:
            if rows:
                add('Transaction review', f'Review unusual {label}',
                    f'{len(rows)} pattern flag(s) in the last 24 hours. These are review signals, not fraud findings.',
                    'Review the audit trail and source records with the owner.')
        return bool(cash.drawer_variances or db.query(models.Order.id).filter_by(restaurant_id=rid).first())

    for name, run in [('profit', profit), ('kitchen', kitchen), ('reservations', reservations), ('cash_fraud', cash_fraud)]:
        before = len(cards)
        try:
            with db.begin_nested():
                has_data = run()
            states[name] = {'state': 'evaluated' if has_data else 'insufficient_data', 'recommendations': len(cards) - before}
        except Exception:
            del cards[before:]
            states[name] = {'state': 'failed', 'recommendations': None}
            logger.exception('Home specialist failed: %s restaurant=%s', name, rid)
    return cards, states
