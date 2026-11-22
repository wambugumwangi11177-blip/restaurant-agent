# Eleven three views — audit (feat/jack-storekeeper)

## Roles & surfaces (this app only)

| View | Login | Frontend | Data scope |
|------|-------|----------|------------|
| **Company OS** (later) | Service token / super-admin JWT | *Not in this repo* | `GET/POST /api/v1/admin/platform/*` |
| **Eleven owner** | `ADMIN` + `owner`, tenant Eleven | `/eleven/*` | Tenant + `restaurant_id` on every store row |
| **Jack** | `STAFF` + `stockkeeper` | `/store/*` | Same tenant; money redaction; no overview/summary |

**Test Restaurant** exists in test seed only to prove the **data wall** in automated tests — not a third in-app UI.

## Data wall

- `restaurant_scope.get_restaurant_or_none` — `active_restaurant_id` must belong to the user's **tenant**.
- Store routers use `get_or_create_restaurant`; no client-sent `restaurant_id` for restaurant users.
- Migration **`j09_data_wall`**: `import_runs` + orphan `inventory_items.restaurant_id` backfill.

## Import

- **In Eleven:** `/eleven/import` + `/api/v1/eleven/import/*` — **Eleven owner ADMIN only**.
- **Company OS:** `/api/v1/admin/platform/restaurants/{id}/import/*` — see **`docs/admin-api.md`**.

## What was removed (scope change)

- No `/super` pages, no client open/close, no `GET /api/v1/super/*` (replaced by **`/api/v1/admin/platform/*`**).

## Jack / owner features retained

- Owner feed: `GET /api/v1/store/approvals`, `GET /api/v1/eleven/summary`.
- Jack: `GET /api/v1/store/my-requests`, `/store/requests`.
- Wall tests: `backend/tests/test_data_wall_eleven.py`.