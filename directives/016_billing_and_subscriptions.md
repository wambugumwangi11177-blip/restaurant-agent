# Directive: Billing & Subscriptions

**Goal**: Charge restaurants for the product, and make non-payment mean
something — without ever stopping a restaurant from trading.

> **Created 2026-08-06.** No directive covered billing before.

## Why this exists

Before this, a subscription was a string an admin set on themselves:

- every tenant was created `plan="free", status="active", provider="manual"`;
- `POST /billing/plan` wrote the field with **no payment gate** — an admin could
  hand themselves `plan="enterprise"` and an active status in one call;
- **no code anywhere read the result.**

The product could collect M-Pesa payments *for* restaurants — a real, careful
Daraja integration — and had no way at all to collect payment *from* them. Every
shilling of the company's own revenue was invoiced by hand, outside the system.

That is the difference between software and a business.

## Architecture

`backend/routers/billing.py`, mounted at `/billing` (and `/api/v1/billing`).
All routes ADMIN-only.

### State machine

```
      new tenant
          │
          ▼
     trialing ──── record-payment ──▶ active
          │                             │
          │  period lapses              │  period lapses
          ▼                             ▼
      (+ GRACE_DAYS)  ──────────▶  past_due  ──── record-payment ──▶ active
                                        │
                                     cancel
                                        ▼
                                    canceled
```

| Constant | Value | Reasoning |
|---|---|---|
| `TRIAL_DAYS` | 14 | New tenants trial rather than sit on free-forever, so the paid state is the default destination and enforcement is exercised from day one instead of switched on later against live restaurants |
| `DEFAULT_PERIOD_DAYS` | 30 | A calendar month is more natural but 30 keeps arithmetic honest across month lengths, and matches the 30-day windows every analytics module uses |
| `GRACE_DAYS` | 3 | M-Pesa payments from an owner arrive when the owner remembers, not on a schedule. Cutting analytics off at midnight on day 30 over money landing on day 31 buys nothing |

### Endpoints
| Endpoint | Purpose |
|---|---|
| `GET /billing/` | Effective (lapse-aware) state, days remaining, grace flag |
| `POST /billing/plan` | Change **tier only** — grants no access time |
| `POST /billing/record-payment` | Money arrived → extend the period |
| `POST /billing/cancel` | Revoke access, keep the period on record |

## Design decisions

-   **Effective status is computed on READ, not by a nightly job.**
    `_effective_status()` treats a stored `active` whose period has passed (plus
    grace) as `past_due` regardless of what the column says. Relying on a
    scheduler would mean enforcement silently fails whenever the scheduler
    doesn't run — and `main.py`'s APScheduler is single-worker, in-process, and
    exactly the kind of thing that stops quietly.

-   **`/billing/plan` does not grant access time.** Only `record-payment` does.
    Splitting these closes the self-service loophole that made billing
    meaningless: upgrading your tier must not pay your bill.

-   **The payment processor stays pluggable.** `provider="manual"` is the
    default and `record-payment` is the human step — an admin confirms the
    M-Pesa till or bank transfer landed. `extend_period()` is the **single seam**
    an M-Pesa-recurring or Stripe adapter calls; no route, schema or gate changes
    when one is wired. For restaurants paying by till number, the manual path
    will never fully go away, so it is the primary path and not a stopgap.

-   **402, not 403.** The caller is correctly authenticated *and* authorised —
    the account owes money. A client can act on that distinction (renewal prompt,
    not access-denied), and it keeps billing failures separable from RBAC
    failures in logs.

-   **A null `current_period_end` is open-ended**, which is what an enterprise
    tenant on an offline contract looks like.

-   **Paying early extends; paying late is not backdated.** `extend_period()`
    bases the new period on whichever is later — now, or the existing end.

## What is gated — and what must NEVER be

`require_active_subscription` is applied **at the router** in `routers/ai.py`, so
every current and future `/ai/*` route inherits it and none can be added later
that quietly bypasses billing.

**Gated:** `/ai/*` — derived intelligence. Pricing recommendations, profit
analysis, simulation, strategy, ROI, marketing. This is the product a restaurant
subscribes to.

**Never gated:** POS, KDS, orders, menu, inventory, reservations, payments, auth,
and `routers/analytics.py` (the main dashboard and the restaurant's own revenue
history).

> **This line must not move.** A restaurant whose payment bounced must still be
> able to take orders and feed people tonight, and must still be able to see its
> own numbers. Locking the till over a billing state would strand a dining room
> mid-service, and any owner it happened to once would tear the system out the
> next morning — correctly.
>
> The principle: **non-payment costs you our analysis, never your ability to
> trade or to see your own data.** `test_an_unpaid_restaurant_can_still_trade`
> exists specifically so nobody moves this line without noticing.

## Still open

-   **No frontend.** No billing page, no renewal prompt, no handling of the 402
    in the UI — an unpaid tenant currently sees a failed request. This is the
    most user-visible gap.
-   **No dunning.** Nothing warns an owner that their period is about to lapse.
    The obvious home is the 07:00 EAT WhatsApp briefing, which already reaches
    exactly the right person.
-   **No invoice or receipt** for the restaurant's own payment.
-   **No proration** on plan change — tiers don't yet differ in what they unlock,
    so there is nothing to prorate. When they do, decide proration before
    shipping the difference.
-   **Plan tiers are cosmetic.** `free` / `pro` / `enterprise` are recorded and
    gate nothing differently. Enforcement is currently binary: active or not.

## Verification

`backend/tests/test_billing.py` (18 tests) covers the trial default, tier change
without access grant, all period arithmetic (early, late, absurd values), grace,
lapse past grace, computed-on-read lapse with a stale stored status, cancel,
open-ended periods, the 402 gate, restoration on payment, and the
must-never-be-gated operational surface.
