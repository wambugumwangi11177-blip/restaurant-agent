# Architecture Decision Records (ADRs)

Short, dated records of significant technical decisions and their rationale. New decisions
get the next number; superseded ADRs are marked, not deleted.

| # | Decision | Status |
|---|---|---|
| [0001](0001-three-layer-architecture.md) | Three-layer directive/orchestration/execution architecture | Accepted |
| [0002](0002-jwt-with-token-version-revocation.md) | Stateless JWT with `token_version` revocation | Accepted |
| [0003](0003-argon2id-password-hashing.md) | Argon2id for password hashing | Accepted |
| [0004](0004-query-layer-tenant-isolation.md) | Query-layer tenant isolation | Accepted |
| [0005](0005-llm-only-on-free-text-path.md) | LLM confined to non-computing roles (free-text + grounded narration); math stays deterministic | Accepted |
| [0006](0006-rbac-via-require-role-dependency.md) | RBAC via a `require_role` dependency | Accepted |

_Owner: Engineering · Contact: leviiiaikenya@gmail.com_
