# ADR 0001 — Modular monolith: one Kernel, departments as isolated packages

**Status:** Accepted, 2026-09-26

## Context
One founder builds and operates the whole OS. The OS must grow department by department (directive 000) without a new department breaking an existing one.

## Decision
- One deployable backend (FastAPI) and one Postgres database.
- `app/kernel/` holds what every department needs: identity, tenancy, RBAC, records, links, events, audit, memory, agent runtime, approvals, channels.
- Each department will be a package `app/departments/<name>/` with its own models, migrations, routes, tools, agents and directive. Departments may import `app.kernel.*`. **They never import each other.** They communicate through Kernel events and records.
- Departments extend the Kernel through registration functions only: `register_permissions`, `register_event_types`, `register_tool`, `register_agent`. They never edit the Kernel's tables.

## Consequences
- One process and one database to run, back up and reason about.
- Isolation is by convention plus review. Add an import-linter rule when the first department lands.
- Split out a service only when one department's load or release cadence genuinely differs, not before.
