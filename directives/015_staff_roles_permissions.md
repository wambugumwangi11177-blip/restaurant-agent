# Directive: Staff Roles & Dashboard Permissions

**Goal**: Replace the current 2-tier (Admin vs Staff), frontend-only access
model with granular, role-scoped dashboard access so a waiter, cook,
stockkeeper, controller, supervisor, manager, and owner each see and can act
on only what their role needs — enforced on the backend, not just hidden nav.

**Status**: Implemented (2026-07-15), alongside
`directives/016_stock_custody_risk_and_staff_comms.md` in the same change
(branch `feat/staff-rbac-stock-custody-twilio`). See that directive's
"As-built notes" for the shared implementation details (migration, tests,
verification). Notes specific to this directive:

- `routers/staff.py` implements the Manager-vs-Owner grant boundary implied
  by (but not explicit in) the matrix below: a Manager can only assign tiers
  Supervisor-and-below; only an Owner can grant Owner or Manager itself —
  otherwise a Manager could mint peer Managers indefinitely. Documented in
  that file's module docstring, not re-litigated per call site.
- The permission matrix below was applied in full to `inventory.py`,
  `menu.py`, `ai.py`, and `analytics.py`'s 6 GET routes. `orders.py` and
  `reservations.py` were deliberately left on their pre-existing
  any-authenticated-user gate rather than tightened to the matrix exactly —
  real remaining work, tracked in 016's as-built notes, not silently done.
- `frontend/dashboard/layout.tsx`'s nav is now driven by the `access` array
  per route (matching the table below) instead of the old `isStaff`/
  `adminOnly` boolean; a `staff_role IS NULL` account gets a dedicated
  "role not assigned yet" screen instead of a broken nav.

## Current state (verified in this codebase, corrected 2026-07-15)

- `backend/models.py: Role` enum has exactly three values: `SUPERADMIN`, `ADMIN`,
  `STAFF`. `STAFF` is **never checked in the backend** — every
  `require_role(...)` call across `routers/ai.py`, `analytics.py`, `billing.py`,
  `enterprise.py`, `events.py`, `export.py` passes `models.Role.ADMIN` only
  (verified: ~51 calls, zero on `STAFF`). **This does not mean STAFF users see
  nothing** — `frontend/src/app/dashboard/layout.tsx` already gives them a
  reduced nav (POS, Kitchen, Orders, Menu, Stock, Bookings, Sales) via an
  `isStaff` check + `adminOnly` flag per nav item, with a client-side redirect
  off admin pages. So today is a **2-tier, frontend-only** split, not
  "ADMIN-or-nothing" — and because the split is client-side only, a STAFF
  user could call an admin API directly and the backend wouldn't stop them.
  Real backend enforcement + 7 tiers instead of 2 is the actual gap this
  directive closes. (The earlier draft of this directive claimed STAFF has
  "no working dashboard access anyway" — that was wrong; corrected here after
  reading `layout.tsx` directly rather than assuming from the backend gate
  alone.)
- `StaffMember` (`models.py` ~line 495) already models a staff roster —
  `restaurant_id`, optional `user_id` (nullable: a staff member can exist for
  payroll/scheduling without ever getting a login), `name`, free-text
  `role_title` (e.g. "Head Chef", "Waiter", "Cashier"), `hourly_rate`,
  `is_active`. This free-text field is descriptive only — it drives no
  permission check today.
- `auth.py: require_role(*allowed_roles)` is the existing dependency factory
  (SUPERADMIN always passes; otherwise checks `current_user.role`). This is the
  hook point to extend, not replace.
- Frontend dashboard routes today (`frontend/src/app/dashboard/*`): `pos`,
  `orders`, `kitchen`, `inventory`, `menu`, `reservations`, `sales`, `roi`, `ai`,
  `ai-ops`, `marketing`. All currently behind the same all-or-nothing session
  check in `frontend/src/app/dashboard/layout.tsx` — no per-section role
  filtering exists.

## Role tiers (7, most → least dashboard scope)

1. **Owner** — everything, including billing/tenant settings, staff account
   creation, all financials. Maps to the existing `Role.ADMIN` system tier
   (do not introduce a parallel concept — an Owner *is* an ADMIN user).
2. **Manager** — full operational access for their restaurant(s): POS, orders,
   kitchen, inventory, menu, reservations, sales/ROI reports, staff scheduling.
   No billing, no tenant-level settings, no creating other Owners.
3. **Supervisor** — shift-level operations: POS, orders, kitchen, reservations,
   read-only sales. No inventory write access, no financial/ROI detail, no
   staff management.
4. **Controller** — the financial/loss-prevention role: inventory reconciliation,
   stock variance reports, sales/ROI read access, audit log read access. Explicitly
   **no POS/order operations** — a controller checks the numbers, doesn't
   generate them, which is the separation-of-duties point of this role (see
   directive 016/017 on stock + risk, not yet written).
5. **Stockkeeper** — inventory only: receiving from supplier, store→kitchen
   transfers, stock counts/adjustments. No POS, no menu, no financial reports.
6. **Kitchen** (Head Cook + Cooks — one tier, `role_title` on `StaffMember`
   distinguishes seniority within it for payroll, not for permissions) — KDS
   only, plus read-only ingredient/recipe view for what they're cooking. No
   inventory write, no financials.
7. **Waiter** — POS/order entry, table status, reservation creation. No
   inventory, no financials, no kitchen ops beyond seeing order status.

## Permission matrix (dashboard route × role)

| Route         | Owner | Manager | Supervisor | Controller | Stockkeeper | Kitchen | Waiter |
|---------------|:-----:|:-------:|:----------:|:----------:|:-----------:|:-------:|:------:|
| `pos`         | RW    | RW      | RW         | –          | –           | –       | RW     |
| `orders`      | RW    | RW      | RW         | R          | –           | R       | RW     |
| `kitchen`     | RW    | RW      | RW         | –          | –           | RW      | R      |
| `inventory`   | RW    | RW      | –          | R          | RW          | R (view only) | – |
| `menu`        | RW    | RW      | R          | –          | –           | R       | R      |
| `reservations`| RW    | RW      | RW         | –          | –           | –       | RW     |
| `sales`       | RW    | RW      | R          | R          | –           | –       | –      |
| `roi`         | RW    | R       | –          | R          | –           | –       | –      |
| `ai` / `ai-ops`| RW   | R       | –          | R          | –           | –       | –      |
| `marketing`   | RW    | RW      | –          | –          | –           | –       | –      |

R = read-only view, RW = can view and act, – = route not shown at all (not
just disabled — absence is intentional, see Edge Cases).

## Architecture

1. **Backend**: add `StaffRole` enum (`OWNER, MANAGER, SUPERVISOR, CONTROLLER,
   STOCKKEEPER, KITCHEN, WAITER`) and a nullable `staff_role` column on `User`
   (migration, additive — existing `Role.ADMIN`/`Role.STAFF` column is
   untouched, this is a second, finer-grained axis layered on top, not a
   replacement).
   - Backfill: existing `Role.ADMIN` users → `StaffRole.OWNER`. Existing
     `Role.STAFF` users → left `NULL` (see Edge Cases — do not guess a tier).
   - New dependency `require_staff_role(*roles)` in `auth.py`, same shape as
     `require_role`, composable with it (`Role.ADMIN`/`SUPERADMIN` still
     always pass, matching current SUPERADMIN-bypass behavior).
   - Embed `staff_role` as a JWT claim (alongside existing `ver` claim) so the
     frontend can filter nav without an extra round-trip.
2. **Frontend**: `dashboard/layout.tsx` reads `staff_role` from the session and
   filters the nav/sidebar to the matrix above; each route additionally
   guards itself (defense in depth — don't rely on hidden nav alone, a
   waiter must not be able to hit `/dashboard/inventory` directly and see
   data even without a link to it).
3. **Staff invitation flow**: when an Owner/Manager creates a `StaffMember`
   with a login (`user_id` set), they must pick one of the 7 tiers at
   creation time — no default silently grants broader access than intended.

## Steps

1. Migration: `staff_role` enum + column on `users`, backfill per above.
2. `auth.py`: add `require_staff_role()`.
3. Apply matrix to each router currently gated only by `require_role(ADMIN)` —
   loosen to `require_staff_role(...)` where the matrix allows non-owner
   access, otherwise leave as Owner/Manager-only.
4. Frontend: nav filtering + per-route guards.
5. Staff management UI: Owner/Manager can create/edit `StaffMember` +
   optional linked `User` + assign one of the 7 tiers.

## Edge Cases

- **`StaffMember.user_id` is nullable by design** — kitchen porters, part-time
  waiters who only clock in/out physically, don't get a login or a
  `staff_role` at all. Don't force every roster entry into this system.
- **No default tier for existing `Role.STAFF` users**: silently assigning a
  tier post-hoc could grant access nobody approved. Surface these as "needs
  role assignment" to the Owner instead of guessing. **Rollout consequence**:
  since these users currently DO reach the operational pages via the
  frontend-only gate (see corrected "Current state" above), backend
  enforcement landing with `staff_role IS NULL` means their very next request
  to a newly-gated write endpoint 403s. `require_staff_role` returns a
  distinguishable `detail` (`"staff_role_unassigned"`) specifically so the
  frontend can render "ask your manager to assign your role" instead of a
  generic permission error — implemented this way rather than defaulting
  NULL to a tier, to honor the "don't guess" decision above without a
  confusing dead-end for the affected user.
- **Multi-restaurant staff**: `staff_role` as a single column on `User` assumes
  one tier per person. A manager at Location A who's only a supervisor at
  Location B isn't representable yet — if that's a real scenario, the tier
  needs to move to a `User × Restaurant` join, not live on `User` directly.
  Flagging as open, not deciding it here.
- **Role changes should be audit-logged** (who promoted/demoted whom, when) —
  ties directly into the theft/risk-prevention workstream (a future
  directive); don't build role-change silently even in this first pass —
  at minimum log it via the existing audit log mechanism if one exists.
- **Controller vs Manager overlap**: Controller is deliberately *read-heavy,
  write-light* even on inventory (reconciliation, not operation) — the
  separation of duties is the point (the person who counts stock
  discrepancies shouldn't be the same person who can also move stock to
  cover for a shortfall). Don't collapse Controller into Manager for
  convenience later.

## Explicitly out of scope for this directive (separate, future directives)

- Supplier → store → kitchen stock movement/chain-of-custody.
- Theft/variance risk detection and Twilio-based automated alerts (the
  Twilio/WhatsApp pipeline already exists — `backend/ai/whatsapp/twilio_client.py`
  — this would extend it, not build new).
- The new-account dashboard bug where AI-agent widgets don't show an
  explained empty state before data exists.
