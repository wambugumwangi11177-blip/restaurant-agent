# Directive 103 — Delivery / Projects

**Records:** project (client, status, dates, budget, `github_repo` as owner/name), milestone (sets `completed_on` automatically), change_request (cost, days of impact), time_entry (minutes, billable; defaults to the person logging it).

**Agents**
| Agent | Kind | On its own | Needs approval |
|---|---|---|---|
| status_reporter | deterministic | draft the weekly status: milestones done, overdue and next; hours; open change requests; GitHub commits | sending it to the client goes through Approvals → Draft an outgoing message |
| scoper | LLM | save a **draft** SOW note with explicit Assumptions and Exclusions; writes TBD instead of inventing dates or prices | — |

**GitHub:** `GET https://api.github.com/repos/{owner}/{repo}/commits?since=…`. Public repos work without a token; private repos need `GITHUB_TOKEN` in the environment. When commits can't be fetched, the report says why rather than guessing.

**Reports:** delivery.projects, delivery.status (parameter `project_id`).

**Access:** founder, staff and contractors write (contractors can't delete); advisors read.

**Done gate:** the Vibanda project status is produced from the OS, not written by hand. Status: ⏳ open (enter the Vibanda project, its milestones and repo).
