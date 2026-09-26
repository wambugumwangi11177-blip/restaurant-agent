# Directive 104 — Support & Incidents

**Records:**
- ticket: priority, status, channel, requester; `sla_due_at` is computed.
- incident: severity, status, timeline, postmortem.

**SLA policy:** the setting `support_sla_hours`, e.g. `urgent=4,high=8,normal=24,low=72`.
- It is **your** policy. There is deliberately no default, because an SLA the OS invented would be a promise you never made.
- Tickets created without a policy have no SLA.

**Rules:**
- Resolving a ticket requires a `resolution`. Past resolutions are what triage learns from.
- `sla_check` (cron every 15 minutes) flags each breached ticket **once**. A ticket counts as breached if it has no first response by its due time. The check notifies founders and emits `ticket.sla_breached`.

**Agents**
| Agent | Kind | On its own | Needs approval |
|---|---|---|---|
| triage | LLM | read the ticket, find similar resolved tickets and docs, judge the priority (explain only; never changes it) | the reply (email or WhatsApp proposal) |
| incident_scribe | deterministic | write a postmortem draft from the recorded timeline, only if none exists; root cause and actions are left as TODO for a human | — |

**Reports:** support.queue, support.incidents.

**Done gate:** every client issue in a 30-day window is a ticket, and SLA breaches are alerted. Status: ⏳ open (set your SLA policy and run it for 30 days).
