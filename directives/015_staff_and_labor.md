# Directive: Staff Roster & Labor Tracking

**Goal**: Capture who worked, for how long, at what cost — so labor analytics
and ROI run on real wages instead of constants.

> **Created 2026-08-06.** No directive covered this before, which is part of why
> the gap below went unnoticed for so long.

## Why this exists

`StaffMember` and `LaborShift` shipped with the labor-intelligence work (Layer 4)
and were read by `ai/labor/intelligence.py` for labor cost %, sales per employee
hour, overtime detection and staffing recommendations.

**Neither table had a writer anywhere in the codebase — not even in
`populate_production.py`, which seeds everything else.** Not one row could ever
exist. Two consequences, both silent:

1. `get_labor_intelligence()` hit its `if not shifts: return _empty_response()`
   branch on every restaurant, always, no matter what they did.
2. `ai/roi/savings.py` fell back to `DEFAULT_HOURLY_RATE_CENTS` (KES 250/hr) for
   its money conversion, so the "hours saved" figure shown to owners was priced
   at a constant rather than at what they actually pay people.

This is the capture-layer principle in directive 001, and it is the clearest
example of it in the codebase: the most complete instance of an analytic with no
possible input.

## Architecture

`backend/routers/staff.py`, mounted at `/staff` (and `/api/v1/staff`).

### Roster
| Endpoint | Role | Notes |
|---|---|---|
| `GET /staff/` | any authed | `?include_inactive=true` to see leavers |
| `POST /staff/` | ADMIN | wages are payroll data |
| `PUT /staff/{id}` | ADMIN | |
| `DELETE /staff/{id}` | ADMIN | **soft delete** — sets `is_active=false` |

### Shifts
| Endpoint | Role | Notes |
|---|---|---|
| `GET /staff/shifts/` | any authed | filters: `start_date`, `end_date`, `staff_member_id` |
| `POST /staff/shifts/` | ADMIN | rostering is a management action |
| `POST /staff/shifts/{id}/clock-in` | any authed | the person on the floor does this |
| `POST /staff/shifts/{id}/clock-out` | any authed | computes hours + cost |
| `DELETE /staff/shifts/{id}` | ADMIN | |

## Design decisions

-   **`hourly_rate` is cents/hour.** So `labor_cost = hours × hourly_rate` is
    already cents — no `× 100`. (Contrast `InventoryItem.cost_per_unit`, which is
    whole KES. The codebase is not consistent about money units; check before
    you multiply. See the unit-boundary warning in directive 007.)

-   **`labor_cost` is computed at clock-out and then frozen.** Recomputing it
    later from the current `hourly_rate` would silently rewrite history every
    time someone got a raise — last month's labor cost % would move under the
    owner's feet. A raise applies to future shifts only.

-   **Clock-in and clock-out are separate endpoints, both idempotent.** They are
    the two events staff actually perform. Clocking in twice keeps the *first*
    timestamp (re-stamping would shorten the shift and undercount labor cost);
    clocking out twice keeps the first close and the cost computed with it.

-   **Clocking is not admin-gated, rostering is.** The person clocking in is the
    staff member; the person setting wages is the owner.

-   **Deactivation is a soft delete.** `LaborShift` rows carry the cost history
    that labor analytics reads over a 30-day window. Hard-deleting a leaver would
    delete last month's labor cost along with them.

-   **Hours are clamped at ≥ 0.** A clock adjustment between in and out must
    never bill negative time.

## Operational notes

-   A restaurant sees nothing from labor intelligence until staff exist **and**
    at least one shift has been clocked out. Add this to onboarding — see
    `backend/LAUNCH_CHECKLIST.md` §7.
-   Overtime threshold is `OVERTIME_HOURS_DAILY = 8.0` in
    `ai/labor/intelligence.py`. It is a constant, not a per-restaurant setting,
    and it is not Kenyan-labour-law-aware. Revisit before making any compliance
    claim about it.
-   Target labor cost is `HEALTHY_LABOR_PCT_MAX = 30.0` of revenue.

## Still open

-   **No frontend.** The API has no UI; staff and shifts must be created via the
    API today. A roster page plus a clock-in screen is the obvious next step, and
    the clock-in screen wants to be usable on a shared tablet.
-   **No link from shift to sales.** `sales_per_hour` divides total revenue by
    total hours across the restaurant; it cannot attribute revenue to the people
    actually on shift at the time. Doing that properly needs the shift window
    intersected with order timestamps.
-   **`StaffMember.user_id`** can link a roster entry to a login but nothing uses
    it yet — e.g. clocking yourself in rather than being clocked in.

## Verification

`backend/tests/test_staff_and_shifts.py` (12 tests) covers hire/list/deactivate,
RBAC, tenant scoping on both roster and shifts, both idempotence paths, the
clock-out-before-clock-in guard, scheduled-hours computation, the frozen-cost
property under a raise, and an end-to-end assertion that
`get_labor_intelligence` stops returning `labor_status: "NO_DATA"`.
