# LEVIII delivery traceability

Source: user-supplied implementation master prompt, 9 November 2026. This file
tracks requirements without republishing private account observations. Baseline:
`master@b5d54e9e0613f1d5416b8a312e24d76fe3f3aef0`. Original reported Phase 1
branch was unavailable; this continuation starts from verified master on
`review/leviii-phase-1-core-evidence-v2`.

**Product status: unfinished. Phase 1 status: in progress, not accepted.**
No merge, production migration, deploy/config change or external message is
authorized by this record. Keep one draft Phase 1 PR; subsequent increments
belong on that branch until Phase 1 acceptance and owner review. Later phases
retain the requested approval checkpoints. Staff UX/framing still needs review.

| ID / prompt source | Existing → proposed reuse or gap | Phase | API / tables | Verification / status |
|---|---|---|---|---|
| P1-POS-01 / §7 | QuickSell webhook → independently committed original envelope | 1 | Existing POST `/webhooks/quicksell/data`; `pos_inbox` | `test_pos_inbox.py`; implemented behind opt-in flag |
| P1-POS-02 / §7 | Mirror deduplication → serialized parsing + DB uniqueness + controlled replay | 1 | `pos_source_bindings`, `pos_applied_records`, `pos_parse_attempts`; POST `/api/v1/pos/quicksell/receipts/{id}/replay` | SQLite retry/failure tests; dedicated PostgreSQL migration/concurrency tests added |
| P1-POS-03 / §2, §7 | Generic Macsoft status → restaurant-specific owner receipt/parser metadata | 1 | GET `/api/v1/pos/quicksell/{status,receipts}`; receipt attempts | Tenant/role/GET-purity tests; no raw PII endpoint |
| P1-POS-04 / §7 | Name lookup → persisted source binding; ambiguous bootstrap fails closed | 1 | `pos_source_bindings` | Rename and ambiguous-name tests; initial binding still needs operator verification |
| P1-POS-05 / §7 | Existing total-only adapter → retain unknown/failed shapes; review unsupported revisions/adjustments | 1 | Inbox status/error codes; existing orders/mirror | Unknown→adapter improvement replay, failed batch, revision tests; full refund/payment/dish reconciliation outstanding |
| P1-AUTH / §1, §6, §9 | Reuse JWT/token-version, Argon2, staff enums → complete restaurant permissions, credential setup and bypass tests | 1 | `users`, memberships/roster; existing auth/staff routes | Existing login preserved; broader authorization work outstanding |
| P1-ITEM / §5–6 | Existing inventory items/movements → explicit Decimal base quantities, conversions, batches, storage vs custody zones | 1 | Inventory/batch/unit/zone additive schema | Outstanding; no stock foundation completion claim |
| P1-RECEIPT / §4–6 | Existing inventory/PO receipt flows → idempotent actual receipts and immutable balanced movements | 1 | Stock movements/receipt provenance | Outstanding |
| P1-HANDOVER / §4–5 | Existing two-party transfers → named chef PIN, version-bound photo/quantity, attempts and lockout | 1 | Stock transfers, private evidence, PIN attempts | Outstanding; required photo framing decision before capture UX |
| P1-SHIFT / §4–5 | Existing attendance/shifts/counts → self-presence, durable once-only start event, two-person/working-alone close | 1 | Attendance/count close/audit/outbox | Outstanding; no new GPS/biometric tracking |
| P1-MISSING / §5 | Existing variance engine → reproducible store-zone Why, explicit kitchen-consumption limitation | 1 | Counts, movements, evidence | Outstanding; discrepancy never proves theft |
| P1-SETUP / §2, §11 | Existing fresh-account script/empty pages → resumable actual setup state and usable owner identity/opening-count forms | 1–2 | Setup reads/explicit authorized writes | Outstanding; this till-evidence page is not the setup workflow |
| P1-MIGRATION / §10 | Existing Alembic head 050 → additive 051 inbox; preserve owners/roles/data | 1 | New inbox schema only | Frozen migration + PostgreSQL tests; full stock migration remains outstanding |
| P2-OWNER / §3, §11 | Reuse all eleven `/eleven` routes and cross-branch owner mockups | 2 | Supported owner APIs/Why; empty/partial/stale/error states | Outstanding; new till evidence is an early Phase 1 review surface only |
| P2-FINANCE / §2–3 | Reuse existing reports/cash and finance models → real input capture and consistent calculations | 2 | Expenses/wages/bills/cash/statements/reports | Outstanding; no imaginary bank integration or empty-match/profit claims |
| P2-ALERTS / §3 | Notifications → real urgency, preferences, acknowledgement/snooze audit | 2 | Alert/read-model/settings routes | Outstanding; routine handovers remain quiet |
| P3-STAFF / §4, §11 | Reuse staff area → shared storekeeper/accountant frontend under individual accounts | 3 | Receipt, chef confirmation, presence, close, export | Blocked on approved staff workflow/design; no broad manager persona |
| P4-EXPIRY / §8, §11 | Batch foundation → expiry-aware FEFO, sourced shelf-life references, waste/valuation | 4 | Batch/waste/ledger | Outstanding; unknown expiry remains unknown |
| P4-ORDERS / §3–4, §11 | Existing supplier/PO features → owner-approved internal task, placed/partial/full actual receipt | 4 | Suppliers/purchase orders/receipts | Outstanding; no autonomous purchase/contact |
| P5-RECIPES / §5, §8, §11 | Existing menu/recipe analytics → historical versions, coverage/yields/POS mapping | 5 | Versioned recipes/sale lines/expected usage | Outstanding; never double-deduct stock |
| P5-FORECAST / §8, §11 | Existing inventory forecasting → gated deterministic baselines/backtests/run-out ranges | 5 | Forecast runs/Why/order suggestions | Outstanding; insufficient history refuses a prediction |
| P5-ASK / §8, §11 | Existing Ask/grounding → authorized fact IDs, numeric/source validation, injection/outage evals | 5 | Read-only allowlisted metrics/answer schema | Outstanding; optional providers need cost/privacy approval |
| ALL-SECURITY / §9–10 | Existing security/CI/recovery docs → evidence as features land | All | RBAC, audits, migrations, CI, private storage | Inbox scope notes in `PHASE1.md`; wider control/privacy/recovery work outstanding |
| RELEASE / §10, §12 | Existing auto-deploy from master → exact reviewed SHA + approved CI/migration/rollback gate | Every release | Protected branch/Railway settings (operator approval) | Unverified, not changed; green checks do not authorize release |

## Dependency order

1. Durable receipt/evidence increment; keep the Phase 1 PR draft.
2. Scoped identities, units/batches/zones, actual receipts/opening counts and
   usable owner setup. Align existing stock engines instead of creating another.
3. Private versioned handover evidence/PIN controls; close/presence/working-alone;
   store-zone Why, concurrency and full Phase 1 acceptance evidence.
4. Stop for Phase 1 review. Owner app → approved staff workflow → expiry/orders →
   recipe/forecast/Ask phases, each with its own review PR.

No reliable total effort or fixed price is asserted before the remaining stock,
credential and count paths are inspected. The deterministic inbox adds database
storage and queries, no model/provider dependency or new hosted worker.
