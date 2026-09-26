# Directive 107 — Marketing & Content

**Records:** campaign, content_piece (idea → draft → review → scheduled → published), consent (the client's permission to be named: who granted it, when, scope, expiry, revocation, signed document).

**Rule** (enforced in code): no case study naming a client without an **active** consent (granted, not expired, not revoked).
- A `case_study` piece can't be scheduled or published without one.
- `save_case_study_draft` refuses to save without one.

**Agents:**
- **case_study_drafter** (LLM): uses recorded project facts only, through the kernel registry. Anything missing, such as metrics or quotes, becomes a `[TODO: ask client]`.
- **content_calendar** (deterministic).

**Reports:** marketing.calendar (next 30 days), marketing.consents.

**Done gate:** one published case study (Vibanda) with their written consent. Status: ⏳ open (needs Vibanda's signed consent).
