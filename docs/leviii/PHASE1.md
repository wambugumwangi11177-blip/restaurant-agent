# Phase 1 working record — durable POS increment

**Phase 1 remains incomplete. This is a draft increment, not a production release.**
See [traceability](TRACEABILITY.md) for every phase and outstanding core work.

## Verified behavior and reuse

Keep the existing Next.js → FastAPI → SQLAlchemy/PostgreSQL modular monolith.
No worker, Redis, model provider, schedule or new hosted service is introduced.
The existing QuickSell URL, `x-api-key`, success response keys and mirror/order
adapter remain compatible for the tested sale shapes. New code reuses those
functions; it does not create a competing sales engine. Total parsing now uses
Decimal/half-up to integer cents, rejecting non-finite/negative/out-of-range
totals and fractional cents instead of silently coercing them.

The optional durable path uses two commits: authenticated bounded UTF-8 JSON →
original envelope commit → source-locked parse/savepoint → mapping/attempt commit.
Mapping failure rolls back all orders/mirror/applied-record writes from that
envelope while keeping the original body and safe error/attempt metadata. A
receipt success is not a successful parse or proof of complete sales coverage.

| Event | Authoritative result | Owner surface |
|---|---|---|
| Authenticated envelope | New `pos_inbox` record and SHA-256 of exact bytes | Receipt ID/time/hash/status only |
| Parser success | Existing mirror + existing orders; applied-identity constraint | Parser status, counts, last success |
| Unknown shape / failed parse | Raw retained, no invented sale; failed batch rolls back | Backlog + fixed error code |
| Owner-authorized replay | Same parser, source row lock, unique applied identity | Actual result, retry-safe repeat |
| Receipt without stable source ID | Compatibility content-hash fallback | Limitation explicitly disclosed |

Receipts record each delivery; equivalent payload retries may generate multiple
receipt records but one mapped sale. Stable record ID + revision is the preferred
identity. Content hashes cannot distinguish identical real sales from retries.
Monotonically increasing integer revisions and ISO timestamp revisions are the
supported ordering assumptions; incomparable/unknown revisions require review.
An already-applied older revision cannot overwrite the current sale. Identical
source identity/version with different content requires review. Refund/void
markers need a future adapter; no automatic reversal or negative-total mapping.
Total-only orders retain existing legacy order semantics, including paid/dine-in
defaults; these are not proof of a payment method, actual settlement or channel.

Initial binding reuses the existing restaurant-name contract only if exactly
one restaurant matches; ambiguity fails closed. The binding persists thereafter,
so a rename cannot redirect the source. No tenant ID/header from the POS selects
the restaurant. Operator verification of the initial binding and a future
multi-source credential design are still release prerequisites.

## APIs and UI

- GET `/api/v1/pos/quicksell/status`: source binding, receipt/parser freshness,
  per-status counts and backlog. No provisioning or provider calls.
- GET `/api/v1/pos/quicksell/receipts?limit=50&offset=0&state=failed`: bounded,
  current-restaurant metadata; no raw customer JSON.
- GET `/api/v1/pos/quicksell/receipts/{id}/attempts`: bounded parser/actor history.
- POST `/api/v1/pos/quicksell/receipts/{id}/replay`: admin owner scope; actual
  impersonated sessions refused. No raw payload editing or arbitrary parser code.
- `/eleven/settings/till`, linked from Settings: empty/loading/error/retained
  failed/parsed states, Nairobi time, Why and real replay. This page does not
  replace stock/identity onboarding or claim all owner pages are implemented.

Admin/superadmin checks reuse the existing account role contract and active
restaurant resolution, with tenant filters on every evidence read/replay. The
broader restaurant membership model is a remaining Phase 1 requirement.

## Threats and evidence

| Boundary / abuse | Control in this increment | Remaining limit |
|---|---|---|
| Forged webhook / oversized or pathological JSON | Existing constant-time key verification; 1 MiB streaming cap, depth 32, 20,000 nodes, batch 500; reject non-finite JSON; duplicate keys retained for review without financial mapping | Key rotation and source operational ownership need review |
| Replayed/concurrent delivery | Source row lock on PostgreSQL; unique source/entity/ID/version mapping; transaction/savepoint | SQLite tests do not prove multiprocess concurrency |
| Parser crash / process interruption | Raw commit precedes mapping; failed/pending queue and controlled replay | No automatic worker is claimed; operator must review backlog |
| Cross-tenant reads/replay | Authenticated current restaurant; scoped queries/FKs, role tests | Full application isolation still requires review |
| Payload/secret leakage | No raw endpoint or SQL exception text in new logs; fixed safe parser error codes | Legacy path/error behavior is not claimed hardened |
| Envelope modification | No mutation API; PostgreSQL trigger prevents raw/scope/time/hash changes | Administrators can alter DB controls; approved retention deletion is separate |
| Malicious source strings / model injection | No provider call or executable source-controlled parser; React renders text | Broader Ask/AI evals belong to Phase 5 |

Draft implementation alignment, not ISO certification or verified formal control
numbering: A.5.15/A.8.3 → scoped evidence API tests; A.8.15/A.5.28 → retained
receipt and safe parse-attempt trail; A.8.26/A.8.29 → compatibility, fault,
scope, revision and PostgreSQL tests; A.8.32 → review-only branch and opt-in
activation. Engineering owns these code controls. Operator owns production
storage, credentials, deployment/backup/retention evidence. Legal/privacy review
owns notices, purposes/lawful basis, international transfer and retention policy.
Do not infer legal compliance or at-rest encryption from these tests.

## Migration, release and recovery (instructions only)

1. Review exact SHA and passing CI, including PostgreSQL evidence. Obtain
   explicit migration/deployment approval and verify the actual Railway CI gate.
2. Rehearse additive `051_pos_durable_inbox` after representative revision 050
   and boot `create_all` → Alembic on isolated PostgreSQL. It creates four tables
   and an envelope immutability trigger; no tenant/owner backfill or data wipe.
3. Verify DB/backup/private retention and source ownership. Existing historical
   mirror events are not silently promoted to raw receipt evidence.
4. Durable mode is **off by default**. Explicitly enable
   `QUICKSELL_DURABLE_INBOX_ENABLED=true` only in an approved environment. This
   work does not change that variable in production. Disabled mode keeps the
   legacy handler and does not claim independent receipt durability.
5. Confirm an authentic permitted delivery using metadata; do not inject fake
   sales into production. Monitor receipt and parse freshness/backlog separately.
6. Forward-fix parser code and replay preserved receipts under owner authority.
   If rolling back, disable durable mode and retain all four tables/evidence.
   The migration deliberately refuses a destructive downgrade; DB deletion
   needs a distinct reviewed retention/recovery decision. Never replay a receipt
   against an arbitrary tenant or delete the reported setup test event.

No raw retention purge is scheduled. Resolve retention periods, legal holds,
backup consistency, least-privilege runtime grants and backlog ownership before
activation. Each delivery can retain up to 1 MiB plus mirror/provenance; no
invented infrastructure price or SLA is asserted.

## Validation record

Exact commands/results are recorded in the draft PR after execution. Tests use
synthetic isolated data and no provider credentials. The PostgreSQL gate extends
the existing `owner-postgres-release` job; no original CI job is removed or
weakened. Container scanning remains non-blocking as in the baseline.

Review checklist: see honest empty/error states; verify a synthetic failed
receipt is retained; replay after an adapter fix creates one sale; a different
tenant cannot see/replay it; repeated completed replay adds no sale; no raw PII
appears in the owner page. Then continue outstanding Phase 1 stock/auth/setup
work, rather than accepting this increment as the complete phase.
