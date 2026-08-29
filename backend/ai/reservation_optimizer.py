"""
Reservation Intelligence — EXHAUSTIVE
================================================================================
Full-depth reservation analytics including:
  1. No-show analysis (overall, by day, by time slot, by party size, by deposit)
  2. No-show probability scoring per future booking
  3. Revenue lost to no-shows (opportunity cost)
  4. Table utilization heatmap (which tables are overworked/underworked)
  5. Revenue per seat per hour (RevPASH)
  6. Average table turnover rate
  7. Booking lead time analysis (how far in advance do guests book?)
  8. Optimal overbooking rate recommendation
  9. Party size distribution analysis
  10. Peak demand windows (which time slots fill fastest?)
  11. Cancellation analysis (rate, timing, patterns)
  12. Deposit impact analysis (conversion effect)
  13. Actionable recommendations with revenue impact estimates

Removed from this list 2026-07-08: "Walk-in vs reservation ratio estimation",
which was never implemented — no function here has ever computed it. It was
cited (by an audit, reading this docstring) as the correction factor available
to fix `avg_spend_per_guest`. It wasn't available, because it didn't exist. If
you add it, `Order.table_number is not null AND no matching reservation` is the
closest signal the schema supports.
================================================================================
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from collections import defaultdict
from datetime import datetime, timedelta
import models
from ai.analysis_clock import analysis_anchor


# Fallback people-per-party when a restaurant has no completed reservation to
# average — two covers per check is the standard casual-dining assumption.
DEFAULT_PARTY_SIZE = 2.0


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
def get_reservation_insights(db: Session, restaurant_id: int) -> dict:
    """Exhaustive reservation intelligence."""
    reservations = db.query(models.Reservation).filter(
        models.Reservation.restaurant_id == restaurant_id
    ).all()

    tables = db.query(models.Table).filter(
        models.Table.restaurant_id == restaurant_id
    ).all()

    if not reservations:
        return _empty_response()

    # Anchored to the restaurant's own most recent reservation, not
    # wall-clock time — see ai/analysis_clock.py's docstring for why (this
    # module isn't order-based, so it anchors to its own data directly
    # rather than importing the order-based helper). Otherwise days_span
    # below counts every day since the restaurant's first reservation up to
    # today as "elapsed," even the days after historical data stops, which
    # dilutes RevPASH and other per-day averages toward zero.
    now = datetime.combine(max(r.reservation_date for r in reservations), datetime.min.time())

    # ── Core Counts ──
    total = len(reservations)
    completed = [r for r in reservations if r.status == models.ReservationStatus.COMPLETED]
    no_shows = [r for r in reservations if r.status == models.ReservationStatus.NO_SHOW]
    cancelled = [r for r in reservations if r.status == models.ReservationStatus.CANCELLED]
    confirmed = [r for r in reservations if r.status == models.ReservationStatus.CONFIRMED]

    # ─────────────────────────────────────────────
    # 1. NO-SHOW ANALYSIS (Deep)
    # ─────────────────────────────────────────────
    no_show_rate = round((len(no_shows) / max(total, 1)) * 100, 1)
    cancel_rate = round((len(cancelled) / max(total, 1)) * 100, 1)
    completion_rate = round((len(completed) / max(total, 1)) * 100, 1)

    # By day-of-week
    dow_data = defaultdict(lambda: {"total": 0, "no_show": 0, "completed": 0})
    for r in reservations:
        day = r.reservation_date.strftime("%A")
        dow_data[day]["total"] += 1
        if r.status == models.ReservationStatus.NO_SHOW:
            dow_data[day]["no_show"] += 1
        elif r.status == models.ReservationStatus.COMPLETED:
            dow_data[day]["completed"] += 1

    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    no_show_by_day = [
        {
            "day": day,
            "total_bookings": dow_data[day]["total"],
            "no_shows": dow_data[day]["no_show"],
            "no_show_rate": round(dow_data[day]["no_show"] / max(dow_data[day]["total"], 1) * 100, 1),
            "completion_rate": round(dow_data[day]["completed"] / max(dow_data[day]["total"], 1) * 100, 1),
        }
        for day in day_order if dow_data[day]["total"] > 0
    ]

    # By time slot
    time_slot_data = defaultdict(lambda: {"total": 0, "no_show": 0})
    for r in reservations:
        slot = _classify_time_slot(r.reservation_time.hour if r.reservation_time else 18)
        time_slot_data[slot]["total"] += 1
        if r.status == models.ReservationStatus.NO_SHOW:
            time_slot_data[slot]["no_show"] += 1

    no_show_by_time = [
        {
            "slot": slot,
            "total": data["total"],
            "no_show_rate": round(data["no_show"] / max(data["total"], 1) * 100, 1),
        }
        for slot, data in sorted(time_slot_data.items())
    ]

    # By party size
    size_data = defaultdict(lambda: {"total": 0, "no_show": 0})
    for r in reservations:
        bucket = _party_size_bucket(r.party_size)
        size_data[bucket]["total"] += 1
        if r.status == models.ReservationStatus.NO_SHOW:
            size_data[bucket]["no_show"] += 1

    no_show_by_party_size = [
        {
            "size_group": bucket,
            "total": data["total"],
            "no_show_rate": round(data["no_show"] / max(data["total"], 1) * 100, 1),
        }
        for bucket, data in sorted(size_data.items())
    ]

    # By deposit status
    with_deposit = [r for r in reservations if r.deposit_paid]
    without_deposit = [r for r in reservations if not r.deposit_paid]
    dep_ns = sum(1 for r in with_deposit if r.status == models.ReservationStatus.NO_SHOW)
    no_dep_ns = sum(1 for r in without_deposit if r.status == models.ReservationStatus.NO_SHOW)

    deposit_analysis = {
        "with_deposit": {
            "total": len(with_deposit),
            "no_shows": dep_ns,
            "no_show_rate": round(dep_ns / max(len(with_deposit), 1) * 100, 1),
        },
        "without_deposit": {
            "total": len(without_deposit),
            "no_shows": no_dep_ns,
            "no_show_rate": round(no_dep_ns / max(len(without_deposit), 1) * 100, 1),
        },
        "deposit_effectiveness": round(
            (1 - dep_ns / max(len(with_deposit), 1)) / max(1 - no_dep_ns / max(len(without_deposit), 1), 0.01) * 100 - 100, 1
        ) if without_deposit else 0,
    }

    no_show_analysis = {
        "total_reservations": total,
        "no_shows": len(no_shows),
        "no_show_rate": no_show_rate,
        "cancellations": len(cancelled),
        "cancel_rate": cancel_rate,
        "completion_rate": completion_rate,
        "no_show_by_day": no_show_by_day,
        "no_show_by_time_slot": no_show_by_time,
        "no_show_by_party_size": no_show_by_party_size,
        "deposit_analysis": deposit_analysis,
    }

    # ─────────────────────────────────────────────
    # 2. REVENUE IMPACT
    # ─────────────────────────────────────────────
    # Three bugs fixed here 2026-07-08, all on the AI-dashboard hot path
    # (ops_manager.get_operations_dashboard -> here):
    #
    #  1. PERF. This used `.all()` over every DINE_IN order the restaurant has
    #     ever taken (~107k rows in prod) and summed them in Python, just to
    #     produce one integer. It's a SQL aggregate — no rows need to cross the
    #     wire. Every other hot module was bounded to 30 days; this was missed.
    #
    #  2. WINDOW SKEW. `avg_spend_per_guest` is a *rate*, and it feeds three
    #     downstream money estimates (revenue_lost_to_no_shows, per-table
    #     revenue, overbooking recovery). Bounding the numerator to 30 days
    #     without bounding the denominator divides one month of revenue by every
    #     guest ever seated, driving the rate — and everything derived from it —
    #     toward zero. Both sides now move together.
    #
    #  3. WRONG DENOMINATOR (the one that made the number nonsense). The rate
    #     divided *all* dine-in revenue by *reserved* guests only. Most covers in
    #     a restaurant are walk-ins, so the denominator was a small fraction of
    #     the people who actually generated the numerator, and the rate was
    #     inflated by 1 / (reservation share of covers). Measured on a smoke
    #     dataset: KES 5,845 "per guest" at a venue whose average check is ~KES
    #     244. The module's docstring advertises "walk-in vs reservation ratio
    #     estimation" as feature #7 — that feature was never implemented, so
    #     there is no ratio to correct with.
    #
    #     `Order` records no guest count, so covers must be estimated. Each
    #     dine-in order is one check, i.e. one party; the reservation book gives
    #     the best available estimate of people per party. So:
    #
    #         covers ≈ dine_in_orders x avg_party_size
    #
    #     This is an estimate and is labelled as one in the payload
    #     (`covers_are_estimated`). It is defensible in a way the old figure was
    #     not: it counts every party that ate, not just the ones that booked.
    #
    # The window anchors to order activity (analysis_clock.analysis_anchor), not
    # to `now` above, because `now` is the last *reservation* date and the two
    # datasets need not end together. If the window is degenerate on either side
    # (imported data whose orders and reservations don't overlap) we fall back to
    # the all-time figures rather than divide by a near-empty denominator.
    order_anchor = analysis_anchor(db, restaurant_id)
    revenue_window_start = order_anchor - timedelta(days=30)

    def _dine_in_totals(since=None) -> tuple[int, int]:
        """(revenue_cents, order_count) for non-cancelled dine-in orders."""
        q = db.query(
            func.coalesce(func.sum(models.Order.total), 0),
            func.count(models.Order.id),
        ).filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.order_type == models.OrderType.DINE_IN,
            models.Order.status != models.OrderStatus.CANCELLED,
        )
        if since is not None:
            q = q.filter(models.Order.created_at >= since)
        revenue, count = q.one()
        return int(revenue or 0), int(count or 0)

    def _avg_party_size(res_list: list) -> float:
        sizes = [r.party_size for r in res_list if r.party_size]
        return (sum(sizes) / len(sizes)) if sizes else DEFAULT_PARTY_SIZE

    windowed_revenue, windowed_orders = _dine_in_totals(since=revenue_window_start)
    windowed_completed = [
        r for r in completed if r.reservation_date >= revenue_window_start.date()
    ]

    # Order count — not revenue — is the "do we have windowed data" signal. A
    # window with real dine-in orders that are all comped/free has revenue 0 but
    # is still valid data; gating on `windowed_revenue` (falsy at 0) would
    # silently discard the correct windowed count and fall back to all-time,
    # reintroducing the window-skew this block exists to prevent.
    if windowed_orders:
        total_dine_revenue = windowed_revenue
        dine_in_orders = windowed_orders
        avg_spend_party = _avg_party_size(windowed_completed or completed)
    else:
        total_dine_revenue, dine_in_orders = _dine_in_totals()
        avg_spend_party = _avg_party_size(completed)

    estimated_covers = max(int(round(dine_in_orders * avg_spend_party)), 1)
    avg_spend_per_guest = int(total_dine_revenue / estimated_covers)

    # Revenue lost to no-shows
    no_show_seats_lost = sum(r.party_size for r in no_shows)
    revenue_lost_to_no_shows = no_show_seats_lost * avg_spend_per_guest

    revenue_impact = {
        "total_dine_in_revenue": total_dine_revenue,
        "avg_spend_per_guest": avg_spend_per_guest,
        "no_show_seats_lost": no_show_seats_lost,
        "estimated_revenue_lost": revenue_lost_to_no_shows,
        "lost_pct_of_dine_revenue": round(revenue_lost_to_no_shows / max(total_dine_revenue, 1) * 100, 1),
        # Provenance for avg_spend_per_guest. `Order` carries no guest count, so
        # covers are inferred (orders x avg party size) rather than counted. Any
        # UI showing the rate should say "estimated"; the reasoning layer grounds
        # numbers against this payload, so the inputs must be here too.
        "dine_in_orders": dine_in_orders,
        "avg_party_size": round(avg_spend_party, 2),
        "estimated_covers": estimated_covers,
        "covers_are_estimated": True,
    }

    # ─────────────────────────────────────────────
    # 3. TABLE UTILIZATION
    # ─────────────────────────────────────────────
    table_utilization = []
    for table in tables:
        table_res = [r for r in reservations if r.table_id == table.id]
        completed_res = [r for r in table_res if r.status == models.ReservationStatus.COMPLETED]
        # Use a local variable name to avoid shadowing the outer avg_spend_party
        table_avg_party = sum(r.party_size for r in table_res) / max(len(table_res), 1)
        seat_utilization = round(table_avg_party / max(table.capacity, 1) * 100, 1)

        # Estimate revenue generated by this table
        table_revenue = len(completed_res) * table_avg_party * avg_spend_per_guest

        table_utilization.append({
            "table_number": table.table_number,
            "capacity": table.capacity,
            "total_bookings": len(table_res),
            "completed": len(completed_res),
            "no_shows": sum(1 for r in table_res if r.status == models.ReservationStatus.NO_SHOW),
            "avg_party_size": round(table_avg_party, 1),
            "seat_utilization_pct": seat_utilization,
            "estimated_revenue": int(table_revenue),
            "rating": "optimal" if 70 <= seat_utilization <= 100 else ("underused" if seat_utilization < 50 else "overbooked"),
        })

    # ─────────────────────────────────────────────
    # 4. RevPASH (Revenue Per Available Seat Hour)
    # ─────────────────────────────────────────────
    total_capacity = sum(t.capacity for t in tables) or 1
    operating_hours = 12  # Assume 12 hours of operation/day
    first_res = min(r.reservation_date for r in reservations)
    days_span = max((now.date() - first_res).days, 1)
    total_seat_hours = total_capacity * operating_hours * days_span

    revpash = {
        "total_seat_hours": total_seat_hours,
        "revpash": round(total_dine_revenue / max(total_seat_hours, 1), 2),
        "avg_turnover_per_day": round(len(reservations) / max(days_span, 1), 1),
        "avg_covers_per_day": round(sum(r.party_size for r in completed) / max(days_span, 1), 1),
    }

    # ─────────────────────────────────────────────
    # 5. BOOKING LEAD TIME ANALYSIS
    # ─────────────────────────────────────────────
    lead_times = []
    for r in reservations:
        if r.created_at:
            lead = (r.reservation_date - r.created_at.date()).days
            if lead >= 0:
                lead_times.append(lead)

    lead_time_analysis = {}
    if lead_times:
        lead_times_sorted = sorted(lead_times)
        n = len(lead_times_sorted)
        lead_time_analysis = {
            "avg_lead_days": round(sum(lead_times) / len(lead_times), 1),
            "median_lead_days": lead_times_sorted[n // 2],
            "min_lead_days": lead_times_sorted[0],
            "max_lead_days": lead_times_sorted[-1],
            "same_day_pct": round(sum(1 for l in lead_times if l == 0) / len(lead_times) * 100, 1),
            "within_week_pct": round(sum(1 for l in lead_times if l <= 7) / len(lead_times) * 100, 1),
            "over_2_weeks_pct": round(sum(1 for l in lead_times if l > 14) / len(lead_times) * 100, 1),
        }

    # ─────────────────────────────────────────────
    # 6. OPTIMAL OVERBOOKING RATE
    # ─────────────────────────────────────────────
    # Simple model: overbook by the historical no-show rate, capped at 20%
    recommended_overbook_pct = min(no_show_rate, 20.0)
    overbook_extra_seats = int(total_capacity * recommended_overbook_pct / 100)
    overbook_recovery = overbook_extra_seats * avg_spend_per_guest * operating_hours

    overbooking = {
        "recommended_overbook_pct": recommended_overbook_pct,
        "extra_seats_to_accept": overbook_extra_seats,
        "estimated_annual_recovery": int(overbook_recovery * 365),
        "risk_note": "Overbooking carries walk-in displacement risk; monitor actual no-show rate monthly.",
    }

    # ─────────────────────────────────────────────
    # 7. PARTY SIZE DISTRIBUTION
    # ─────────────────────────────────────────────
    party_dist = defaultdict(int)
    for r in reservations:
        party_dist[r.party_size] += 1

    party_size_distribution = [
        {
            "party_size": size,
            "count": count,
            "pct": round(count / max(total, 1) * 100, 1),
        }
        for size, count in sorted(party_dist.items())
    ]

    # ─────────────────────────────────────────────
    # 8. PEAK DEMAND WINDOWS
    # ─────────────────────────────────────────────
    slot_fill_times = defaultdict(list)  # slot -> list of lead_days
    for r in reservations:
        if r.created_at:
            slot = _classify_time_slot(r.reservation_time.hour if r.reservation_time else 18)
            lead = (r.reservation_date - r.created_at.date()).days
            if lead >= 0:
                slot_fill_times[slot].append(lead)

    peak_demand = [
        {
            "slot": slot,
            "booking_count": len(leads),
            "avg_lead_days": round(sum(leads) / len(leads), 1) if leads else 0,
            "fills_fastest": sum(leads) / len(leads) < 3 if leads else False,
        }
        for slot, leads in sorted(slot_fill_times.items())
    ]

    # ─────────────────────────────────────────────
    # 9. CANCELLATION ANALYSIS
    # ─────────────────────────────────────────────
    cancel_lead_times = []
    for r in cancelled:
        if r.created_at:
            lead = (r.reservation_date - r.created_at.date()).days
            if lead >= 0:
                cancel_lead_times.append(lead)

    cancellation_analysis = {
        "total_cancellations": len(cancelled),
        "cancel_rate": cancel_rate,
        "avg_cancel_lead_days": round(sum(cancel_lead_times) / len(cancel_lead_times), 1) if cancel_lead_times else 0,
        "last_minute_cancels": sum(1 for l in cancel_lead_times if l <= 1),
        "last_minute_pct": round(sum(1 for l in cancel_lead_times if l <= 1) / max(len(cancel_lead_times), 1) * 100, 1),
    }

    # ─────────────────────────────────────────────
    # 10. ACTIONABLE RECOMMENDATIONS
    # ─────────────────────────────────────────────
    recommendations = _build_recommendations(
        no_show_rate=no_show_rate,
        cancel_rate=cancel_rate,
        deposit_analysis=deposit_analysis,
        table_utilization=table_utilization,
        revenue_lost=revenue_lost_to_no_shows,
        avg_spend=avg_spend_per_guest,
        recommended_overbook_pct=recommended_overbook_pct,
    )

    return {
        "no_show_analysis": no_show_analysis,
        "revenue_impact": revenue_impact,
        "table_utilization": table_utilization,
        "revpash": revpash,
        "lead_time_analysis": lead_time_analysis,
        "overbooking_recommendation": overbooking,
        "party_size_distribution": party_size_distribution,
        "peak_demand_windows": peak_demand,
        "cancellation_analysis": cancellation_analysis,
        "recommendations": recommendations,
    }


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _classify_time_slot(hour: int) -> str:
    if hour < 11:
        return "breakfast (before 11)"
    elif hour < 14:
        return "lunch (11-14)"
    elif hour < 17:
        return "afternoon (14-17)"
    elif hour < 20:
        return "dinner (17-20)"
    else:
        return "late dinner (20+)"


def _party_size_bucket(size: int) -> str:
    if size <= 2:
        return "1-2 (couple/solo)"
    elif size <= 4:
        return "3-4 (small group)"
    elif size <= 6:
        return "5-6 (medium group)"
    else:
        return "7+ (large group)"


def _build_recommendations(
    no_show_rate: float,
    cancel_rate: float,
    deposit_analysis: dict,
    table_utilization: list,
    revenue_lost: float,
    avg_spend: float,
    recommended_overbook_pct: float,
) -> list:
    recs = []

    if no_show_rate > 15:
        recs.append({
            "priority": "high",
            "category": "no_shows",
            "action": "Require deposits for all bookings",
            "rationale": f"No-show rate is {no_show_rate}% — above the 15% threshold where deposits pay for themselves.",
            "estimated_revenue_impact": int(revenue_lost * 0.6),
        })
    elif no_show_rate > 8:
        recs.append({
            "priority": "medium",
            "category": "no_shows",
            "action": "Send SMS/email reminders 24h and 2h before reservation",
            "rationale": f"No-show rate of {no_show_rate}% can typically be reduced 30-40% with reminders.",
            "estimated_revenue_impact": int(revenue_lost * 0.35),
        })

    dep = deposit_analysis
    if dep["without_deposit"]["total"] > 10 and dep["without_deposit"]["no_show_rate"] > dep["with_deposit"]["no_show_rate"] + 5:
        recs.append({
            "priority": "high",
            "category": "deposits",
            "action": "Expand deposit requirement to all reservation types",
            "rationale": (
                f"Guests without deposits no-show at {dep['without_deposit']['no_show_rate']}% "
                f"vs {dep['with_deposit']['no_show_rate']}% with deposits."
            ),
            "estimated_revenue_impact": int(
                dep["without_deposit"]["no_shows"] * avg_spend * 0.7
            ),
        })

    underused = [t for t in table_utilization if t["rating"] == "underused"]
    if underused:
        recs.append({
            "priority": "medium",
            "category": "table_utilization",
            "action": f"Promote tables {[t['table_number'] for t in underused]} for walk-ins or smaller parties",
            "rationale": f"{len(underused)} table(s) are consistently underutilized (<50% seat fill).",
            "estimated_revenue_impact": int(len(underused) * avg_spend * 2),
        })

    if cancel_rate > 20:
        recs.append({
            "priority": "medium",
            "category": "cancellations",
            "action": "Introduce a 24-hour cancellation policy with partial deposit forfeiture",
            "rationale": f"Cancellation rate of {cancel_rate}% is high; a policy reduces last-minute gaps.",
            "estimated_revenue_impact": 0,
        })

    if recommended_overbook_pct >= 5:
        recs.append({
            "priority": "low",
            "category": "overbooking",
            "action": f"Accept {recommended_overbook_pct}% overbooking on peak nights",
            "rationale": "Historical no-show rate supports controlled overbooking to fill seats.",
            "estimated_revenue_impact": 0,
        })

    return recs


def _empty_response() -> dict:
    return {
        "no_show_analysis": {},
        "revenue_impact": {},
        "table_utilization": [],
        "revpash": {},
        "lead_time_analysis": {},
        "overbooking_recommendation": {},
        "party_size_distribution": [],
        "peak_demand_windows": [],
        "cancellation_analysis": {},
        "recommendations": [],
    }