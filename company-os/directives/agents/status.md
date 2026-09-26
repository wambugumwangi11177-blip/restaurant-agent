# Agent: status (deterministic)

Produces "what needs me right now" for the requesting member: approvals waiting
(with their summaries), open / due-today / overdue tasks, accepted decisions whose
revisit date has arrived, and unread notifications. Reads only; no LLM.

Triggered from the web shell (Agents page), the API (`POST /agents/status/run`)
and WhatsApp (message `status` from a member's registered phone).
