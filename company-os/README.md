# Company OS

The company's internal operating system: one **Kernel** (identity, records, memory, agents, approvals, audit), with **departments** built on top of it one at a time.

- **Plan:** [`directives/000_company_os_plan.md`](directives/000_company_os_plan.md)
- **Kernel SOP and done-gate status:** [`directives/001_kernel.md`](directives/001_kernel.md)
- **Decisions:** [`docs/adr/`](docs/adr/README.md)
- **Operations:** [`RUNBOOK.md`](RUNBOOK.md)
- **Departments:** Command Center (101), Sales (102), Delivery (103), Support (104), Finance (105), Legal (106), Marketing (107), Product (108), People (109), Productize (110). The directives are in `directives/`.

## Principles
- Agents propose, deterministic code executes, and the founder approves anything that leaves the company.
- Every write is scoped to a workspace, audited (append-only, no PII) and emitted as an event.
- "Learning" means company memory with citations, a feedback log of every approve, edit and reject, and evals that gate changes. It never means changing model weights.

## Quick start
```bash
./dev.sh    # needs Postgres 16 at DATABASE_URL (default: cos:cos@localhost/cos_dev)
python execution/bootstrap_workspace.py --slug <company> --name "<Company>" --email <you> --full-name "<You>"
```
Then open http://localhost:3000. The full steps are in directive 001.

## Layout
```
backend/     FastAPI + SQLAlchemy + Alembic (app/kernel = the Kernel, app/departments = one module per department, app/api = HTTP)
frontend/    Next.js web shell (approvals, records, memory, agents, audit)
directives/  SOPs; directives/agents/*.md are agent system prompts
execution/   deterministic scripts (bootstrap, ingest, CSV import, scheduled jobs, evals, backup, restore drill)
evals/       retrieval eval cases and baseline
docs/adr/    architecture decisions
```

## Moving to its own repository
This folder is self-contained. Once the `company-os` GitHub repo exists:
```bash
git subtree split --prefix=company-os -b company-os-export
git push git@github.com:<owner>/company-os.git company-os-export:main
```
Then move `.github/workflows/company-os.yml` into the new repo and remove its `company-os/` path prefixes (ADR 0007).
