# Source-system integration contract (v0.1 — DRAFT, needs client answers)

Status: DRAFT. Integration code MUST NOT be written until every required answer is filled.

## 1. Identification
- Client system name / vendor: <<>>
- Version: <<>>
- Deployment: <<cloud | on-prem | hybrid>>
- Who administers it: <<name, contact>>
- Who can grant API or export access: <<name, contact>>

## 2. Access mechanism (answer ALL FOUR; "unknown" blocks the workstream)
- [ ] REST/GraphQL API — base URL: <<>>, auth method: <<api key | oauth2 | mTLS | session>>
- [ ] Database read replica — engine/version: <<>>, allowed schemas: <<>>
- [ ] Scheduled file export — format: <<CSV | JSON | XML | SQL dump>>, cadence: <<>>, delivery: <<SFTP | S3 | email>>
- [ ] Webhooks/event stream — events available: <<>>, delivery guarantee: <<at-least-once | at-most-once | exactly-once>>

## 3. Entities to mirror (map their name → our name; mark N/A where absent)
| Their entity | Our table | Key fields | Notes |
|---|---|---|---|
| <<e.g. Item / Product>> | `menu_items` | name, price, category, active | |
| <<e.g. Tender / Sales>> | `orders`, `order_items` | id, timestamp, line items, total | |
| <<e.g. Inventory count>> | `inventory_items`, `stock_movements` | sku, qty, unit | |
| <<e.g. Employee>> | `staff` | id, role, active | |
| <<e.g. Supplier>> | `suppliers` | name, lead time | |

## 4. Identity and idempotency (REQUIRED)
- Stable primary key exposed to us for each entity: <<>>
- Is it immutable? <<>>
- Monotonic change signal (updated_at / version / sequence / rowversion): <<>>
- Can records be hard-deleted on their side? <<yes/no — how do we learn about it?>>
- Timezone of all timestamps: <<>> (state explicitly; a wrong tz silently corrupts every daily aggregate)

## 5. Volume and cadence (REQUIRED)
- Rows/day: orders <<>>, order lines <<>>, stock movements <<>>
- Full history to backfill: <<months/GB>>
- Acceptable sync latency: <<minutes>>
- Maintenance windows / rate limits: <<>>

## 6. Data-protection constraints
- Personal data present: <<names, phones, emails, ID numbers?>>
- Contractual limits on copying/storing/processing: <<>>
- Retention requirement for mirrored data: <<>>
- Regional/legal constraint (e.g. Kenya DPA 2019): <<>>

## 7. Ownership and failure semantics
- Who owns reconciliation when a count differs: <<>>
- On ingest failure, must the mirror be frozen or degraded-with-alert: <<>>
- Who is paged: <<>>

## 8. Sign-off
- Client sign-off: <<name, date, mechanism (email/ticket/LoI)>>
- Our sign-off: <<name, date>>
