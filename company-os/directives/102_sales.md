# Directive 102 — Customers & Sales

**Records:** deal (stage, value in minor units plus currency, next step and its date, owner, lost reason), activity (call, email, meeting, WhatsApp, note). Organizations and people are kernel records.

**Rules** (enforced in code):
- A lost deal requires `lost_reason`.
- `closed_at` is set when a deal is won or lost.
- Logging an activity updates the deal's `last_activity_at`.
- **Next-step rule:** an open deal is flagged when it has no next step, no date on the next step, an overdue next step, or no activity for `sales_stale_days` (default 14, a setting).

**Agents**
| Agent | Kind | On its own | Needs approval |
|---|---|---|---|
| pipeline_reviewer | deterministic | list rule-breaking deals | — |
| followup_drafter | LLM | read the deal, search memory | every email or WhatsApp (proposal) |
| research_organizer | LLM | save an **UNVERIFIED** profile note from pasted research | — |

The OS has **no web-search provider**, so research_organizer only organizes what you paste. It never "looks things up".

**Reports:** sales.pipeline (per stage, totals per currency; no exchange rates), sales.stale.

**Import:** `execution/import_records.py --type organization|person|deal --map "Your column=field"`. Map your CRM export's columns; no export format is assumed.

**Access:** founder and staff write; advisors read; contractors have no access.

**Done gate:** every live conversation is in the CRM, and no deal goes 14 days without a next step. Status: ⏳ open (needs your real pipeline imported).
