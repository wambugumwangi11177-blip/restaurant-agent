---
name: staff-roles-permissions
description: Implement or extend role-based dashboard access for the restaurant-agent app — the 7-tier staff model (Owner, Manager, Supervisor, Controller, Stockkeeper, Kitchen, Waiter) and which dashboard sections/actions each can see. Use this whenever asked to add staff accounts, change who-can-see-what, gate a route/endpoint by role, add RBAC, or touch the User/StaffMember models, auth.py's require_role, or the dashboard nav/layout. Also use it to audit whether an existing route is over- or under-permissioned. Do not use the generic code-review skill for this — that reviews diffs, this designs and implements the permission model itself.
---

# Staff Roles & Dashboard Permissions

## Source of truth

`directives/015_staff_roles_permissions.md` is the living spec — read it
first, every time. If what you find in the code has drifted from what it
says, update the directive (don't silently route around the mismatch — that's
this repo's CLAUDE.md "self-annealing" rule: fix it, then write down what you
learned).

## Ground yourself before writing anything

Never assume a column, dependency, or helper exists — grep/read it. Facts
already verified as of the last pass (re-verify if it's been a while):

- `backend/models.py`: `Role` enum is only `SUPERADMIN / ADMIN / STAFF`.
  `STAFF` is defined but **not gated anywhere** in the routers today — it's
  effectively a binary ADMIN-or-nothing system.
- Every `require_role(...)` call across `routers/ai.py`, `analytics.py`,
  `billing.py`, `enterprise.py`, `events.py`, `export.py` passes
  `models.Role.ADMIN` only. Grep `require_role(models.Role` before assuming
  any route's current gate.
- `StaffMember` (`models.py`, search `class StaffMember`): `restaurant_id`
  required, `user_id` **nullable** (a roster entry can exist with no login —
  don't force one), free-text `role_title` ("Head Chef", "Waiter", "Cashier")
  that drives no permission logic today.
- `auth.py`: `require_role(*allowed_roles)` is the existing dependency
  factory (SUPERADMIN always passes). This is the extension point — add a
  parallel `require_staff_role()`, don't replace it.
- `frontend/src/app/dashboard/layout.tsx`: gating today is a single
  `isStaff` boolean per nav item (`adminOnly` flag). This is what the 7-tier
  matrix replaces.
- Dashboard routes that exist right now: `pos`, `orders`, `kitchen`,
  `inventory`, `menu`, `reservations`, `sales`, `roi`, `ai`, `ai-ops`,
  `marketing`.

## The 7 tiers and the permission matrix

Defined in full in directive 015 — the table below is a quick-reference copy,
but treat the directive as canonical if they ever diverge.

| Route          | Owner | Manager | Supervisor | Controller | Stockkeeper | Kitchen | Waiter |
|----------------|:-----:|:-------:|:----------:|:----------:|:-----------:|:-------:|:------:|
| `pos`          | RW    | RW      | RW         | –          | –           | –       | RW     |
| `orders`       | RW    | RW      | RW         | R          | –           | R       | RW     |
| `kitchen`      | RW    | RW      | RW         | –          | –           | RW      | R      |
| `inventory`    | RW    | RW      | –          | R          | RW          | R       | –      |
| `menu`         | RW    | RW      | R          | –          | –           | R       | R      |
| `reservations` | RW    | RW      | RW         | –          | –           | –       | RW     |
| `sales`        | RW    | RW      | R          | R          | –           | –       | –      |
| `roi`          | RW    | R       | –          | R          | –           | –       | –      |
| `ai` / `ai-ops`| RW    | R       | –          | R          | –           | –       | –      |
| `marketing`    | RW    | RW      | –          | –          | –           | –       | –      |

R = read-only, RW = view + act, – = route not shown at all.

**Owner maps onto the existing `Role.ADMIN` system tier — it is not a new,
parallel concept.** Everything else is a second, finer-grained column that
layers on top of the existing `Role` enum; don't touch `Role` itself.

**Controller is deliberately read-heavy, write-light even on inventory.**
That's the separation-of-duties point: the person reconciling stock variance
shouldn't be the same person who can move stock to cover a shortfall. Don't
collapse Controller into Manager for convenience.

## Implementation sequence

1. **Migration**: add `StaffRole` enum (`OWNER, MANAGER, SUPERVISOR,
   CONTROLLER, STOCKKEEPER, KITCHEN, WAITER`) + nullable `staff_role` column
   on `User`, alembic-style like the existing migrations in
   `backend/alembic/versions/`. Backfill: existing `Role.ADMIN` users →
   `StaffRole.OWNER`. Existing `Role.STAFF` users → leave `NULL` — don't
   guess a tier for them (see Edge Cases).
2. **`auth.py`**: add `require_staff_role(*roles)`, same shape as
   `require_role` (SUPERADMIN/ADMIN bypass, matching current behavior).
   Embed `staff_role` as a JWT claim alongside the existing `ver` claim.
3. **Routers**: apply the matrix. Where the matrix allows non-Owner access,
   loosen from `require_role(ADMIN)` to `require_staff_role(...)`; where it
   doesn't, leave it Owner/Manager-only.
4. **Frontend**: `dashboard/layout.tsx` filters nav by `staff_role` from the
   session (replacing the single `isStaff` boolean); each route additionally
   guards itself server-side via the backend change above — don't rely on
   hidden nav links alone, a Waiter must not be able to hit `/dashboard/inventory`
   directly and get real data back just because there's no link to it.
5. **Staff invite/edit UI**: Owner/Manager creating a `StaffMember` with a
   login (`user_id` set) must pick one of the 7 tiers at creation time — no
   default that silently grants more access than intended.
6. **Audit logging**: log every role assignment/change (who changed whom,
   when) — least-privilege access control is only as good as its audit
   trail; if a theft investigation ever needs "who had access," this is
   where that answer comes from. Reuse this repo's existing audit-log
   mechanism if one exists (check `backend/models.py` and `routers/` for
   anything already logging admin actions before building a new one).

## Verify before calling it done

- Run the backend test suite (`backend/pytest.ini` — check
  `backend/tests/` for the existing RBAC-adjacent tests, e.g. anything
  named `test_tenant_isolation.py` or similar, and extend rather than
  duplicate).
- Confirm the migration is idempotent and reversible (matches the pattern
  other migrations in `backend/alembic/versions/` already follow).
- Manually smoke-test login as at least Owner + one restricted tier (e.g.
  Waiter) and confirm the nav and the underlying API both agree — a 403 from
  the API with a visible nav link is a bug, and so is the reverse.

## Edge cases (from directive 015 — don't relitigate these, they were already decided)

- `StaffMember.user_id` stays nullable by design — not every roster entry
  gets a login.
- Existing `Role.STAFF` users get no default tier — surface them to the
  Owner as "needs role assignment" instead of guessing, since nothing gates
  on `STAFF` today so they have no working access to preserve anyway.
- One `staff_role` column assumes one tier per person. A manager at one
  location who's only a supervisor at another isn't representable yet — if
  that's a real scenario, it needs to move to a `User × Restaurant` join.
  This is a known open question, not a bug to silently patch around.

## When you're done

Update `directives/015_staff_roles_permissions.md` with anything you learned
that wasn't already in it (an API constraint, a migration gotcha, a decision
that got made) — directives are living documents, not one-shot specs.
