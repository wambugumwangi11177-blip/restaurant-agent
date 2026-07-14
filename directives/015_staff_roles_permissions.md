# Directive: Staff Roles & Dashboard Permissions

**Goal**: Replace the current binary "ADMIN or nothing" access model with granular,
role-scoped dashboard access so a waiter, cook, stockkeeper, controller, supervisor,
manager, and owner each see and can act on only what their role needs.

**Status**: Draft — spec only, no code changes yet. Review before implementation starts.

## Current state (verified in this codebase, 2026-07-14)

- `backend/models.py: Role` enum has exactly three values: `SUPERADMIN`, `ADMIN`,
  `STAFF`. `STAFF` exists but is **not actually gated anywhere** — every
  `require_role(...)` call across `routers/ai.py`, `analytics.py`, `billing.py`,
  `enterprise.py`, `events.py`, `export.py` passes `models.Role.ADMIN` only. In
  practice today it's binary: you're the restaurant admin, or you have no access
  at all. This is very likely the root of the "new account's dashboard looks the
  same but some of it doesn't show" complaint — there's no per-role dashboard yet,
  so nothing conditionally renders by who's logged in.
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
- **No default tier for existing `Role.STAFF` users**: they currently have no
  working dashboard access anyway (nothing gates on `STAFF` today), so
  silently assigning a tier post-hoc could grant access nobody approved.
  Surface these as "needs role assignment" to the Owner instead of guessing.
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
