# ADR 0008 — Departments plug into the Kernel through registries

**Status:** Accepted, 2026-09-26

## Context
Nine departments had to be built without each one copying CRUD, audit, permission and UI code, and without departments depending on each other (ADR 0001).

## Decision
A department is one module, `app/departments/<name>.py`, with SQLAlchemy models, its own Alembic migration, and a `register()` function that calls Kernel registries:
- `records.register_record_type`: the generic `/records/{type}` API, with workspace scoping, audit, events, `refs` checks, per-type permissions, and `prepare` / `after` hooks for computed fields
- `rbac.register_permissions`, `events.register_event_types`
- `departments.register_report | register_job | register_setting | register_brief_section | register_department`
- `tools.register_tool`, `registry.register_agent`

The web UI is generated from `GET /records-types`, which is derived from each type's Pydantic schema. A new department needs no frontend code.

**Reading across departments** (for example Product reading Sales deal values, or Marketing reading Delivery projects) goes through the Kernel record registry, and only when the other department is enabled. There are no imports. Such a read degrades gracefully ("sales not enabled").

Workspaces can enable a subset of departments (`workspaces.enabled_departments`). A disabled department's records, reports and jobs return 404.

## Consequences
- Adding a department means one module, one migration, one directive and tests.
- Cross-department reads couple to field names such as `deal.value_minor`. A department that renames a field must check `grep -r RECORD_TYPES\[` for readers.
