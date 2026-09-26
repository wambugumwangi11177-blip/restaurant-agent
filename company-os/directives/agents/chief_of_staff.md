# Agent: chief_of_staff (deterministic)

Builds the daily brief from the following:
- Kernel status: approvals, tasks, decisions to revisit, notifications
- Today's events from the founder's private iCal URL (recurring events are counted, not expanded)
- Goals that are at risk or off track
- One section from each enabled department (sales follow-ups, overdue invoices, SLA breaches, obligations due, and so on)

It makes no LLM call. The `daily_brief` job sends the same text every morning.
