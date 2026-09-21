# Vibanda Village — Macsoft mapping worksheet

Complete this worksheet with Macsoft before registering a real adapter. Do not
put credentials, connection strings or raw customer data in this file.

| Topic | Required evidence | Confirmed value |
| --- | --- | --- |
| Product and hosting | Exact product/version; cloud or on-premise | Pending |
| Authorization | Approved Vibanda location IDs and read-only scope | Pending |
| Access method | Supported API, read-only view, or export; technical contact | Pending |
| Connectivity | Auth scheme, TLS/VPN/IP constraints, expiry, rate limits | Pending |
| Sales | Stable sale/line IDs, statuses, taxes, discounts, service charges | Pending |
| Tenders | IDs, allocation, split/partial tenders, refunds and reversals | Pending |
| Time | Source timezone, business cutoff, close/finalization marker | Pending |
| Corrections | Updated timestamp/change feed, cancellations/deletions | Pending |
| Completeness | Pagination, snapshots, retention and source totals | Pending |
| Other modules | Stock, costs, purchasing, shifts, kitchen, bookings, audit | Pending |
| Reconciliation | Normal and exception closed-day report plus sanitized rows | Pending |
| Operations | Maintenance, schema change process, escalation and cost | Pending |

## Export-only pilot

If Macsoft supplies exports rather than an API, run the validation-only CSV
probe with a reviewed mapping. It reports aggregate structural quality
(counts, duplicates, malformed timestamps/amounts and statuses) without
persisting source rows. An export pilot is periodic data, never a live feed.
