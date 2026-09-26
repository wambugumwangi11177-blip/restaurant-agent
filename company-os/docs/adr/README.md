# Architecture Decision Records

Each ADR records one decision, why it was made, and what it costs. Supersede an ADR with a new one rather than editing history.

| # | Decision | Status |
|---|---|---|
| 0001 | Modular monolith: one Kernel, departments as isolated packages | Accepted |
| 0002 | The approval gate lives in the tool runtime, not in prompts | Accepted |
| 0003 | Postgres full-text search before vector search | Accepted |
| 0004 | Tests run on real PostgreSQL, never SQLite | Accepted |
| 0005 | Provider-neutral LLM layer; Anthropic via official SDK | Accepted |
| 0006 | Audit log is append-only and never stores PII | Accepted |
| 0007 | Build inside restaurant-agent until the company-os repo exists | Accepted (temporary) |
| 0008 | Departments plug into the Kernel through registries | Accepted |
