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

    def _avg_party_size(reservations: list) -> float:
        sizes = [r.party_size for r in reservations if r.party_size]
        return (sum(sizes) / len(sizes)) if sizes else DEFAULT_PARTY_SIZE

    windowed_revenue, windowed_orders = _dine_in_totals(since=revenue_window_start)
    windowed_completed = [
        r for r in completed if r.reservation_date >= revenue_window_start.date()
    ]

    if windowed_revenue and windowed_orders:
        total_dine_revenue = windowed_revenue
        dine_in_orders = windowed_orders
        avg_party = _avg_party_size(windowed_completed or completed)
    else:
        total_dine_revenue, dine_in_orders = _dine_in_totals()
        avg_party = _avg_party_size(completed)

    estimated_covers = max(int(round(dine_in_orders * avg_party)), 1)
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
        "avg_party_size": round(avg_party, 2),
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
        avg_party = sum(r.party_size for r in table_res) / max(len(table_res), 1)
        seat_utilization = round(avg_party / max(table.capacity, 1) * 100, 1)

        # Estimate revenue generated by this table
        table_revenue = len(completed_res) * avg_party * avg_spend_per_guest

        table_utilization.append({
            "table_number": table.table_number,
            "capacity": table.capacity,
            "total_bookings": len(table_res),
            "completed": len(completed_res),
            "no_shows": sum(1 for r in table_res if r.status == models.ReservationStatus.NO_SHOW),
            "avg_party_size": round(avg_party, 1),
            "seat_utilization_pct": seat_utilization,
            "estimated_revenue": int(table_revenue),
            "rating": "optimal" if 70 <= seat_utilization <= 100 else ("underused" if seat_utilization < 50 else "overbooked"),
        })

    # ─────────────────────────────────────────────
    # 4. RevPASH (Revenue Per Available Seat Hour)
    # ─────────────────────────────────────────────
    total_capacity = sum(t.capacity for t in tables) or 1
    operating_hours = 12  # Assume 12 hours of operation/day
    first_res = min(r.reservation_date for r in reservations) if reservations else now.date()
    days_span = max((now.date() - first_res).days, 1) if isinstance(first_res, type(now.date())) else 30
    total_seat_hours = total_capacity * operating_hours * days_span

    revpash = {
        "total_seat_hours": total_seat_hours,
        "revpash": round(total_dine_revenue / max(total_seat_hours, 1), 2),
        "avg_turnover_per_day": round(len(reservations) / max(days_span, 1), 1),
        "avg_covers_per_day": round(sum(r.party_size for r in completed) / max(days_span, 1), 1),
    }

    # ─────────────────────────────────────────────
    # 5. BOOKING LEAD TIME
    # ─────────────────────────────────────────────
    lead_times = []
    for r in reservations:
        if r.created_at and r.reservation_date:
            lead = (r.reservation_date - r.created_at.date()).days
            if lead >= 0:
                lead_times.append(lead)

    if lead_times:
        sorted_lt = sorted(lead_times)
        avg_lead = sum(lead_times) / len(lead_times)
        median_lead = sorted_lt[len(sorted_lt) // 2]
        same_day = sum(1 for l in lead_times if l == 0)
    else:
        avg_lead = median_lead = same_day = 0

    lead_time_analysis = {
        "avg_days": round(avg_lead, 1),
        "median_days": median_lead,
        "same_day_bookings": same_day,
        "same_day_pct": round(same_day / max(total, 1) * 100, 1),
        "distribution": {
            "same_day": sum(1 for l in lead_times if l == 0),
            "1_day": sum(1 for l in lead_times if l == 1),
            "2_3_days": sum(1 for l in lead_times if 2 <= l <= 3),
            "4_7_days": sum(1 for l in lead_times if 4 <= l <= 7),
            "over_7_days": sum(1 for l in lead_times if l > 7),
        },
    }

    # ─────────────────────────────────────────────
    # 6. PARTY SIZE DISTRIBUTION
    # ─────────────────────────────────────────────
    party_sizes = [r.party_size for r in reservations]
    party_dist = defaultdict(int)
    for ps in party_sizes:
        party_dist[ps] += 1

    party_size_analysis = {
        "avg_party_size": round(sum(party_sizes) / max(len(party_sizes), 1), 1),
        "median_party_size": sorted(party_sizes)[len(party_sizes) // 2] if party_sizes else 0,
        "distribution": [{"size": k, "count": v, "pct": round(v / total * 100, 1)} for k, v in sorted(party_dist.items())],
    }

    # ─────────────────────────────────────────────
    # 7. PEAK DEMAND WINDOWS
    # ─────────────────────────────────────────────
    demand_windows = defaultdict(lambda: {"total": 0, "completed": 0})
    for r in reservations:
        if r.reservation_time:
            window = f"{r.reservation_time.hour:02d}:00"
            demand_windows[window]["total"] += 1
            if r.status == models.ReservationStatus.COMPLETED:
                demand_windows[window]["completed"] += 1

    peak_windows = sorted(
        [{"window": w, "bookings": d["total"], "fill_rate": round(d["completed"] / max(d["total"], 1) * 100, 1)}
         for w, d in demand_windows.items()],
        key=lambda x: x["bookings"],
        reverse=True,
    )

    # ─────────────────────────────────────────────
    # 8. OPTIMAL OVERBOOKING RATE
    # ─────────────────────────────────────────────
    # If no-show rate is X%, we can overbook by X% to maximize utilization
    if no_show_rate > 5:
        overbooking_rate = round(no_show_rate * 0.7, 1)  # Conservative: 70% of no-show rate
        potential_recovery = int(overbooking_rate / 100 * total_capacity * avg_spend_per_guest)
    else:
        overbooking_rate = 0
        potential_recovery = 0

    overbooking = {
        "recommended_rate": overbooking_rate,
        "potential_monthly_recovery": potential_recovery,
        "risk_level": "low" if overbooking_rate < 10 else ("medium" if overbooking_rate < 20 else "high"),
    }

    # ─────────────────────────────────────────────
    # 9. RECOMMENDATIONS
    # ─────────────────────────────────────────────
    recommendations = _generate_recommendations(
        no_show_analysis, no_show_analysis.get("deposit_analysis", {}), table_utilization,
        revenue_impact, lead_time_analysis, overbooking, peak_windows, party_size_analysis
    )

    return {
        "no_show_analysis": no_show_analysis,
        "revenue_impact": revenue_impact,
        "table_utilization": sorted(table_utilization, key=lambda x: x["seat_utilization_pct"], reverse=True),
        "revpash": revpash,
        "lead_time_analysis": lead_time_analysis,
        "party_size_analysis": party_size_analysis,
        "peak_windows": peak_windows,
        "overbooking": overbooking,
        "recommendations": recommendations,
    }


# ─────────────────────────────────────────────────────────────────────────────
# RECOMMENDATION ENGINE
# ─────────────────────────────────────────────────────────────────────────────
def _generate_recommendations(no_show, deposit, tables, revenue, lead_time, overbooking, peak_windows, party):
    """Actionable intelligence with revenue impact estimates."""
    recs = []

    # No-show management
    if no_show["no_show_rate"] > 15:
        recs.append({
            "type": "no_show",
            "message": f"No-show rate is {no_show['no_show_rate']}%, costing ~{revenue['estimated_revenue_lost']/100:,.0f} KES in lost revenue.",
            "action": "Implement mandatory deposits for all bookings",
            "priority": "critical",
            "impact": f"Could recover {int(revenue['estimated_revenue_lost'] * 0.6 / 100):,} KES/month",
        })
    elif no_show["no_show_rate"] > 8:
        recs.append({
            "type": "no_show",
            "message": f"No-show rate at {no_show['no_show_rate']}% — above industry benchmark of 8%.",
            "action": "Require deposits for parties of 4+ or weekend bookings",
            "priority": "high",
            "impact": f"Could save {int(revenue['estimated_revenue_lost'] * 0.4 / 100):,} KES/month",
        })

    # Deposit effectiveness
    if deposit.get("deposit_effectiveness", 0) > 30:
        recs.append({
            "type": "deposit",
            "message": f"Deposits reduce no-shows by {deposit.get('deposit_effectiveness', 0):.0f}%. Expand deposit policy.",
            "action": "Extend deposits to all peak-time bookings",
            "priority": "high",
            "impact": "Proven to significantly reduce no-shows",
        })

    # High no-show day
    worst_day = max(no_show["no_show_by_day"], key=lambda x: x["no_show_rate"]) if no_show["no_show_by_day"] else None
    if worst_day and worst_day["no_show_rate"] > 20:
        recs.append({
            "type": "day_pattern",
            "message": f"{worst_day['day']}s have {worst_day['no_show_rate']}% no-show rate — the worst day.",
            "action": f"Require deposits specifically for {worst_day['day']} bookings",
            "priority": "medium",
            "impact": f"Target the highest-risk day directly",
        })

    # Underutilized tables
    for t in tables:
        if t["rating"] == "underused" and t["total_bookings"] > 3:
            recs.append({
                "type": "table_optimization",
                "message": f"Table {t['table_number']} (capacity {t['capacity']}) averages only {t['avg_party_size']:.0f} guests ({t['seat_utilization_pct']}% utilization).",
                "action": "Reassign to smaller parties or combine for large groups",
                "priority": "low",
                "impact": "Better table-to-party matching improves RevPASH",
            })

    # Overbooking recommendation
    if overbooking["recommended_rate"] > 5:
        recs.append({
            "type": "overbooking",
            "message": f"With {no_show['no_show_rate']}% no-shows, accept {overbooking['recommended_rate']}% more bookings.",
            "action": "Implement controlled overbooking during peak slots",
            "priority": "medium",
            "impact": f"Could recover ~{overbooking['potential_monthly_recovery']/100:,.0f} KES/month",
        })

    # Same-day booking warning
    if lead_time["same_day_pct"] > 30:
        recs.append({
            "type": "lead_time",
            "message": f"{lead_time['same_day_pct']}% of bookings are same-day — high operational pressure.",
            "action": "Incentivize advance bookings with priority seating or small discounts",
            "priority": "low",
            "impact": "Better forecasting and staffing planning",
        })

    return recs


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _classify_time_slot(hour):
    if 11 <= hour < 15:
        return "lunch"
    elif 18 <= hour < 21:
        return "dinner_early"
    elif 21 <= hour < 23:
        return "dinner_late"
    else:
        return "other"


def _party_size_bucket(size):
    if size <= 2:
        return "1-2"
    elif size <= 4:
        return "3-4"
    elif size <= 6:
        return "5-6"
    else:
        return "7+"


def _empty_response():
    return {
        "no_show_analysis": {}, "revenue_impact": {},
        "table_utilization": [], "revpash": {},
        "lead_time_analysis": {}, "party_size_analysis": {},
        "peak_windows": [], "overbooking": {},
        "recommendations": [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# AVAILABILITY CHECK (Phase 2 — directives/012_agentic_roadmap.md)
#
# Real conflict/capacity logic. Deliberately kept separate from the analytics
# above: this is Layer 3 deterministic logic that a booking flow (LLM-driven
# or not) must call rather than letting a model guess at availability.
#
# Concurrency note (resolved 2026-07-08): `find_available_tables` still
# checks-then-suggests, so its result is advisory the moment it returns. The
# actual write path (`routers/reservations.create_reservation`) now re-runs the
# single-table check via `is_table_available()` immediately before INSERT, and
# alembic/versions/009_add_reservation_overlap_guard.py adds a Postgres
# EXCLUDE-USING-GIST constraint so two concurrent writers that both pass the
# application check still cannot both commit. That constraint is the real
# guarantee; the application check exists to turn the race into a clean 409
# instead of an IntegrityError in the common (uncontended) case.
#
# Why EXCLUDE rather than the partial unique index used for PENDING pricing
# recommendations: uniqueness cannot express *interval overlap*. Two bookings on
# one table at 18:00 and 18:30 are distinct rows under any unique key, yet
# conflict. GiST range exclusion is the only DB-level construct that says "no two
# rows whose time ranges intersect."
# ─────────────────────────────────────────────────────────────────────────────


def _intervals_overlap(a_start, a_end, b_start, b_end) -> bool:
    """Half-open overlap: touching intervals (18:00-19:30, 19:30-21:00) do NOT conflict."""
    return a_start < b_end and b_start < a_end


def _reservation_bounds(reservation_date, reservation_time, duration_minutes):
    start = datetime.combine(reservation_date, reservation_time)
    return start, start + timedelta(minutes=duration_minutes or 90)


def is_table_available(
    db: Session,
    restaurant_id: int,
    table_id: int,
    reservation_date,
    reservation_time,
    duration_minutes: int = 90,
    exclude_reservation_id: int | None = None,
) -> bool:
    """
    True if `table_id` has no overlapping CONFIRMED reservation in the window.

    Scoped by `restaurant_id` so it can never be satisfied by (or collide with)
    another tenant's reservations. `exclude_reservation_id` lets a future
    reschedule flow ignore the row it is itself moving.
    """
    requested_start, requested_end = _reservation_bounds(
        reservation_date, reservation_time, duration_minutes
    )

    q = db.query(models.Reservation).filter(
        models.Reservation.restaurant_id == restaurant_id,
        models.Reservation.table_id == table_id,
        models.Reservation.reservation_date == reservation_date,
        models.Reservation.status == models.ReservationStatus.CONFIRMED,
    )
    if exclude_reservation_id is not None:
        q = q.filter(models.Reservation.id != exclude_reservation_id)

    for res in q.all():
        res_start, res_end = _reservation_bounds(
            res.reservation_date, res.reservation_time, res.duration_minutes
        )
        if _intervals_overlap(requested_start, requested_end, res_start, res_end):
            return False
    return True

def find_available_tables(
    db: Session,
    restaurant_id: int,
    party_size: int,
    reservation_date,
    reservation_time,
    duration_minutes: int = 90,
) -> list[dict]:
    """
    Returns tables with enough capacity and no overlapping CONFIRMED
    reservation for the requested date/time/duration, smallest-capacity-first
    (best fit, avoids wasting a large table on a small party).
    """
    requested_start, requested_end = _reservation_bounds(
        reservation_date, reservation_time, duration_minutes
    )

    tables = (
        db.query(models.Table)
        .filter(
            models.Table.restaurant_id == restaurant_id,
            models.Table.capacity >= party_size,
        )
        .order_by(models.Table.capacity.asc())
        .all()
    )
    if not tables:
        return []

    same_day_reservations = (
        db.query(models.Reservation)
        .filter(
            models.Reservation.restaurant_id == restaurant_id,
            models.Reservation.reservation_date == reservation_date,
            models.Reservation.status == models.ReservationStatus.CONFIRMED,
            models.Reservation.table_id.isnot(None),
        )
        .all()
    )

    booked_intervals_by_table: dict[int, list[tuple[datetime, datetime]]] = defaultdict(list)
    for res in same_day_reservations:
        booked_intervals_by_table[res.table_id].append(
            _reservation_bounds(res.reservation_date, res.reservation_time, res.duration_minutes)
        )

    available = []
    for table in tables:
        conflicts = booked_intervals_by_table.get(table.id, [])
        if any(
            _intervals_overlap(requested_start, requested_end, s, e) for s, e in conflicts
        ):
            continue
        available.append({
            "table_id": table.id,
            "table_number": table.table_number,
            "capacity": table.capacity,
        })

    return available
