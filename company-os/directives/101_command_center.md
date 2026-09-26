# Directive 101 — Founder Command Center

**Purpose:** one screen and one WhatsApp message a day that tell the founder what matters.

**Records:** goal (metric, baseline, target, current, status), meeting. Tasks, decisions and notes are kernel records.

**Agents**
| Agent | Kind | Can do on its own | Needs approval |
|---|---|---|---|
| chief_of_staff | deterministic | compose the brief | — |
| decision_recorder | LLM | create decisions with status **proposed** | nothing leaves the company; the founder accepts a decision by setting it to accepted |

**Daily brief** (`daily_brief` job, cron 07:00 Africa/Nairobi via `execution/run_jobs.py daily_brief`) contains:
- Kernel status: approvals, tasks, decisions to revisit
- Today's calendar
- Goals at risk or off track
- One section from each enabled department

It's delivered as an in-app notification, and by WhatsApp when the founder has a phone number and Twilio is configured. Members are internal, so it goes without approval.

**Calendar:** set `calendar_ical_url` in Settings. In Google Calendar that's Settings → your calendar → "Secret address in iCal format". It's stored masked, and only the key name reaches the audit log.
- Supported: timed events and all-day events.
- Recurring events are **not expanded**; they are counted and flagged in the brief.
- A failing calendar never breaks the brief.

**Reports:** command.brief, command.goals, command.calendar

**Done gate** (from directive 000): the founder uses the brief for 10 consecutive working days, and every item links to its source record.
Status: ⏳ **open**. The software is built and tested; the gate needs real use.

**Founder must supply:** the iCal URL, a phone number on their member profile, Twilio credentials, and a cron entry for `daily_brief`.

**Known limitations:** no RRULE expansion; progress is computed as (current − baseline) / (target − baseline).
