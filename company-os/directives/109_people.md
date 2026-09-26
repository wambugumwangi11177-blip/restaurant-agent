# Directive 109 — People & HR (founder only; used from the first hire)

**Records:** staff_record (links to a person and optionally a Company OS user; kind; status: onboarding / active / offboarding / left), checklist_item, access_grant (system, account, granted, revoked).

**Agents** (deterministic)
- **onboarding:** adds your checklist from the `onboarding_checklist` setting (one item per line). Without it, a minimal default list is used. It is idempotent.
- **offboarding:** marks the person offboarding and adds one "Revoke <system>" item per active access grant, plus removing Company OS membership and collecting devices. External systems can't be revoked by the OS, so they become checklist items.

**Report:** people.access_risk lists people offboarding or gone who still hold active access. Also: people.roster.

**Not built in:** employment-law rules (notice, leave, statutory payroll deductions). Take those from your lawyer or accountant.

**Done gate:** not applicable until the first hire. The first onboarding runs through the OS.
