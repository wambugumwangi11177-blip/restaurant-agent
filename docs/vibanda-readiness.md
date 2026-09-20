# Vibanda Village readiness record

## Purpose

This branch prepares the owner-facing read-only experience while Macsoft
remains the operational source of truth. It is not a production certification
or a claim that Macsoft is connected.

## Tracer-bullet path

`Macsoft (read-only) -> approved adapter -> validated facts -> Home / Ask / Reports`

- `FEATURE_OBSERVER_MODE=true` is a server-enforced, fail-closed boundary.
  It blocks operational mutations, legacy fact routes, webhooks, Support, AI
  actions, event subscribers and the operational scheduler.
- `NEXT_PUBLIC_OBSERVER_MODE=true` exposes only Home, Ask and Reports, each
  showing a source-unavailable state until a validated source is connected.
- `RestaurantSource` is a bounded read-only adapter contract. Its default is
  `UnconfiguredSource`, so no local application records can be inferred to be
  Macsoft facts.
- Daily, Monday-start weekly, monthly and yearly periods use half-open
  `Africa/Nairobi` calendar boundaries.
- The synthetic demonstration path is restricted to staging, requires both an
  environment gate and a command-line acknowledgement, and creates only the
  explicitly labelled `Vibanda Village — Synthetic` tenant with 60 days of
  fixtures. It must never be used for a real restaurant or source proof.

## Current verification

- Python syntax compilation completed for the new observer, source, reporting
  and synthetic-seed modules.
- Direct checks passed for Nairobi period boundaries and integer minor-unit
  money aggregation with explicit status semantics.
- The branch is intended to run the full test suite in GitHub Actions through
  a pull request; no local dependency install, server, database import or
  production build was used.

## Release gates still requiring external evidence

1. Macsoft product/version, approved read-only access method and authorized
   Vibanda location ID.
2. Sanitized schema/export plus a normal and exception-containing closed-day
   report for reconciliation of sales, tenders, refunds, voids and corrections.
3. Business-day cutoff, historical retention, report retention and supported
   module coverage.
4. Isolated staging database and authenticated deployment access. The staging
   deployment must not receive production credentials or a live Macsoft write
   capability.
5. Pull-request CI, preview smoke test, tenant isolation, sign-in/recovery and
   mobile acceptance evidence before a client release.
