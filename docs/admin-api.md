# Company OS — platform admin API (headless)

The Eleven **frontend has no client list or switcher**. Multi-client operations are for the separate **Company OS** project, which calls this API on the Jack test / production backend.

Base path: **`/api/v1/admin/platform`**

## Authentication

Use **one** of:

1. **`Authorization: Bearer <jwt>`** — user must have `role: superadmin` (same JWT as `/api/v1/auth/login`).
2. **`X-Company-OS-Token: <secret>`** — must match server env **`COMPANY_OS_SERVICE_TOKEN`** (never commit). Auditing uses **`COMPANY_OS_ACTOR_EMAIL`** (default `wambugu@leviii.ai`) as the acting user.

Restaurant users and Eleven owners get **403** on every route below.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/restaurants` | List restaurants: tenant name, `restaurant_id`, staff login count, `last_import_at`, `setup_complete` |
| POST | `/restaurants` | Create tenant + first restaurant (`tenant_name`, `restaurant_name`, `address`) |
| POST | `/restaurants/{restaurant_id}/staff` | Create staff login (`email`, `staff_role`, `display_name`) |
| GET | `/restaurants/{restaurant_id}/import-runs` | Import audit log for that restaurant |
| GET | `/import/template` | Download `.xlsx` template |
| POST | `/restaurants/{restaurant_id}/import/preview` | Multipart file → preview JSON |
| POST | `/restaurants/{restaurant_id}/import/confirm` | Multipart file → apply import for **that** `restaurant_id` only |

Imports write `import_runs` and respect the same workbook format as Eleven owner import (`eleven_import`).

## Eleven app import (in-product)

Owners with **`ADMIN`** on tenant **Eleven** use **`/api/v1/eleven/import/*`** and **`/eleven/import`** in the UI. That path never accepts a client-supplied `restaurant_id`; it always resolves the signed-in owner's Eleven restaurant server-side.

## Environment (test stacks)

```bash
COMPANY_OS_SERVICE_TOKEN=<long-random>
COMPANY_OS_ACTOR_EMAIL=wambugu@leviii.ai
```

Unset `COMPANY_OS_SERVICE_TOKEN` disables service-token auth (Bearer super-admin only).