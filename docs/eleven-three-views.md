# Eleven three views — audit (feat/jack-storekeeper)

## Roles & surfaces

| Login tier | `Role` / `staff_role` | Frontend home | API scope |
|------------|----------------------|---------------|-----------|
| **Super-admin** (Wambugu / Gift) | `SUPERADMIN` | `/super` client list → open one client | `active_restaurant_id` may point at **any** restaurant; `/api/v1/super/*` only for `SUPERADMIN` |
| **Eleven owner** | `ADMIN` + `owner` | `/eleven/*` | Tenant **Eleven** only; `get_restaurant_or_none` + `restaurant_id` on every store row |
| **Jack (storekeeper)** | `STAFF` + `stockkeeper` | `/store/*` | Same tenant restaurant; money redaction middleware; no `/overview`, no `/super` |

## What already existed

- **Store chain** (`store_intake`, `store_control`, `store_day`, `store_recipes`): queries filter `restaurant.id` from `get_or_create_restaurant` — no client-sent `restaurant_id`.
- **Owner feed**: `GET /api/v1/store/approvals` (cards, pending Jack requests, honest quiet states).
- **Jack flows**: suppliers, deliveries, issue, waste, counts, day photos, questionnaires, approvals pipeline.
- **Import**: `eleven_import` (owner ADMIN) — was **Eleven-tenant-name gated only**, not super-admin multi-client.
- **Handover**: `eleven_handover` — tenant-scoped login list; `GET /eleven/logins/admin` SUPERADMIN-only (no UI).
- **PIN / APK**: `AppLockGate`, solid panels in APK — unchanged by this work.

## Gaps found (this batch)

| Gap | Fix |
|-----|-----|
| SUPERADMIN could not open **Test Restaurant** without sharing owner login | `/super/clients` + `POST /super/open/{restaurant_id}` |
| Test APK workflow pointed at production frontend once | `device-packages-test.yml` hardcoded `frontend-test` host (prior commit) |
| No **import audit log** with failed rows | `import_runs` table + log on confirm |
| `InventoryItem.restaurant_id` nullable (legacy) | Migration **j09** backfill to tenant’s primary restaurant |
| No wall tests across **Eleven vs Test Restaurant** | `test_data_wall_eleven.py` |
| Owner `/eleven/reports` sales slice thin | `GET /api/v1/eleven/summary` — sales only when orders exist; stock value needs cost |

## `restaurant_id` on tables

**Jack / store parent rows** (all NOT NULL): `StockBalance`, `DeliveryReceipt`, `Supplier`, `SpoilageRecord`, `ImportAppliedKey`, `StaffSetupProgress`, etc.

**Scoped via FK** (no direct column): receipt lines, photo checks, handover lines.

**Legacy watchlist**: `InventoryItem.restaurant_id` (nullable → backfilled in j09); `StockMovement` (scoped via `inventory_item_id` in queries).

**User**: `tenant_id` + optional `active_restaurant_id` (super-admin may set cross-tenant).

## Chakula / dead routes

`test_rbac.test_legacy_chakula_routes_not_mounted` — `/menu`, old demo paths return 404. No Chakula branding in LEVIII frontend (`PRODUCT_NAME = "LEVIII"`).