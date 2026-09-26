# ADR 0007 — Build inside restaurant-agent until the company-os repo exists

**Status:** Accepted (temporary), 2026-09-26

## Context
The founder chose a separate `company-os` repository. The GitHub integration available to the build session returned `403 Resource not accessible by integration` when creating it.

## Decision
- Develop in `restaurant-agent/company-os/`, fully self-contained: no imports from restaurant-agent, its own CI workflow scoped to this path, and its own dependencies.
- When the repo exists, extract it with history:
  `git subtree split --prefix=company-os -b company-os-export`, then push that branch to the new repo's `main`.
  Move `.github/workflows/company-os.yml` into the new repo's `.github/workflows/` and drop the `company-os/` path prefixes.

## Consequences
- restaurant-agent's own CI and deployments are untouched.
