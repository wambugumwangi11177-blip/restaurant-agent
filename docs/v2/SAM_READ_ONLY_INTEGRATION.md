# Eleven POS integration brief for Sam

Draft for Mbuguss to review with Sam. Not sent. No database access has been attempted.

## Goal
LEVIII reads Eleven sales for reporting and recommendations. It does not update the POS, its prices, inventory, users or payments. LEVIII's own staff entries remain in its separate database. Approval of a LEVIII suggestion must not imply a write to the POS.

## Ask Sam first
1. POS product/version, database engine/version, and hosting/network arrangement.
2. Whether Eleven has a dedicated database or shares one with other customers; exact Eleven company and branch identifiers.
3. Whether he can expose versioned Eleven-only read views or an export/API instead of unrestricted tables.
4. Available sale, sale-line, payment, menu and refund/void fields; anonymized sample rows and field definitions.
5. Stable primary keys, update timestamps/change sequence, deletion/void semantics, timezone, currency and whether amounts include tax/discounts.
6. Connection method: approved TLS/private network, read replica where possible, query/time limits and maintenance hours.

## Least-privilege access contract
- Prefer a dedicated account with SELECT only on approved Eleven-only views in a reporting schema; no DDL/DML, stored-procedure execution, ownership, cross-customer tables or administrative privileges.
- In a shared database, server-enforced tenant filtering is mandatory. An application WHERE clause alone does not isolate Eleven.
- Verify the effective permissions with Sam and a disposable/sample environment, including denied attempts to read a second customer. Do not test writes against production merely to prove they fail.
- Credentials stay in the deployment secret store, never source control, screenshots, messages or this document. Require encryption and certificate validation.
- Use bounded incremental reads with a stable (updated_at, source_id) cursor, overlap/replay deduplication and resumable checkpoints. Define deletions explicitly; do not silently omit changed historical sales.

## Minimum source contract
| Entity | Required fields |
|---|---|
| Branch | stable branch ID, name, Eleven company ID |
| Sale | stable sale ID, branch ID, opened/paid/updated timestamps, currency, total in exact minor units, payment and cancellation state |
| Sale line | stable line ID, sale ID, product ID/name, quantity/unit, unit price, discounts/tax, final line amount |
| Payment | stable payment ID, sale ID, method, amount, paid timestamp, reversal state; M-Pesa receipt if actually recorded |
| Product | stable product ID, branch/menu scope, name, price, active flag |
| Correction | original record reference, refund/void amount, timestamp, reason where available |

Never infer missing receipts, costs, staff identities or physical stock counts. Explicitly mark absent fields and data coverage. Avoid customer names/phone numbers unless a separately agreed feature needs them.

## Acceptance before live sync
- Sam supplies one representative quiet day and one busy day, including midnight/06:00 boundary, split payments, refunds and voids.
- Reconcile order count, gross/net sales, discounts/taxes, and tender totals per branch to the POS's own export.
- Repeat the same import: no additional rows or changed totals. Edit/refund an old sale in the sample: one correct update appears.
- Simulate disconnect/restart and bounded backfill; no lost/duplicated data and no expensive whole-table scan every cycle.
- Verify Eleven-only access and an agreed query load. Stage first; then controlled activation with freshness/error monitoring and a stop-sync switch.

Pending: Sam's engine/schema/sample/access method. Until supplied, implementation of a real database connector is blocked; the existing MacSoft integration cannot be assumed compatible.
