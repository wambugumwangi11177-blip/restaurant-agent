# Legal-Pack Redline Change-List

| | |
|---|---|
| **Reference** | LAI-REDLINE-001 |
| **Classification** | Internal |
| **Version** | 1.1 |
| **Last Updated** | 2026-07-11 |
| **Owner** | Engineering + Legal (Leviii AI Technologies) |
| **Contact** | leviiiaikenya@gmail.com |

## Purpose

The 12-document legal/security pack (LAI-SEC-001 … LAI-KRA-001) is generated **outside this
repository** — its source files are not version-controlled here. This document is therefore
a **redline change-list**: apply each edit at the source, wherever the pack is authored.

Every change below is driven by the code audit recorded in
[control-evidence-matrix.md](control-evidence-matrix.md). Each entry gives the **document +
section**, the **current text** (quote it to locate the passage), the **proposed
replacement**, and the **reason**.

Priority key: **P1** = corrects an over-claim (do first) · **P2** = precision/consistency ·
**P3** = polish/credibility.

---

## Part 1 — Accuracy corrections (claims that outrun the code)

### R-01 · P1 · LAI-SEC-001 §05 — RBAC enforcement
- **Status update (2026-07-11):** Track B1 has **shipped**. A `require_role` dependency now
  enforces roles (`backend/auth.py`), applied to admin-sensitive routes (data
  export/erasure, AI usage, restaurant-profile update), covered by `test_rbac.py`
  (STAFF → 403, ADMIN/SUPERADMIN → allowed). Enforcement is real but **coverage is still
  expanding** to the full "STAFF = POS/KDS only" surface.
- **Proposed wording (accurate today):**
  > *"Roles are enforced on data-export, data-erasure, AI-observability, and restaurant-
  > profile endpoints via a role-check dependency; SUPERADMIN has full access. Per-role
  > coverage across the remaining operational endpoints is being progressively expanded so
  > that STAFF accounts are limited to POS and Kitchen Display functions."*
- **When RBAC coverage is complete:** restore the original strong table wording ("STAFF —
  Operational access — POS and Kitchen Display only") verbatim; it will then be literally
  true. Track this against Control Evidence Matrix open-item 1.

### R-02 · P1 · LAI-SEC-001 §05 — "Minimum complexity enforced at registration"
- **Status update (2026-07-11):** Track B2 has **shipped**. `require_strong_password`
  (`backend/auth.py`) enforces a minimum of 8 characters including at least one letter and
  one digit at registration, covered by `test_rbac.py`. The original claim is now true.
- **Proposed wording (accurate today):** keep *"Minimum complexity enforced at
  registration"* and, if useful, specify: *"minimum 8 characters, including letters and
  numbers."* No interim softening needed.

### R-03 · P2 · LAI-SEC-001 §04 (In Transit) — "HTTP automatically redirected"
- **Current:** *"HTTPS enforced on all endpoints — HTTP automatically redirected"*.
- **Reality:** TLS is terminated at the Railway edge; the redirect/enforcement happens at
  the platform layer, not in application code (`backend/middleware/security_headers.py:9-12`).
- **Proposed:** *"HTTPS enforced at the platform edge (Railway-managed TLS termination);
  the application additionally sets HSTS on every response."* — accurate and still strong.

### R-04 · P2 · LAI-SEC-001 §06 (Insecure Deserialization / Injection) — "strict type validation"
- **Current:** *"Pydantic strict type validation on all request bodies"*.
- **Reality:** request bodies are validated against typed Pydantic schemas, but strict mode
  / `extra="forbid"` is not set (`backend/schemas.py`).
- **Proposed:** *"Typed Pydantic schema validation on all request bodies (rejecting
  type-mismatched input)."* — Optionally restore "strict" after Track B3 adds
  `extra="forbid"`.

### R-05 · P2 · LAI-SEC-001 §04 (At Rest) — AES-256 attribution
- **Current:** *"Database encryption at rest: AES-256, managed by Neon PostgreSQL"*.
- **Reality:** correct, but provider-managed with no in-repo evidence.
- **Proposed:** keep the claim, add attribution — *"…managed by Neon PostgreSQL
  (provider-managed; see Neon's SOC 2 Type II report). This is an infrastructure control,
  not an application control."* Prevents a reader assuming Leviii AI implements at-rest
  crypto itself.

### R-06 · P2 · LAI-DPA-001 §04 vs LAI-SEC-001 §06 / LAI-AI-001 §03 — audit-log retention conflict
- **Current:** DPA §04 lists *"Audit logs — 90 days rolling"*; SEC and AI describe the AI
  audit table as *"append-only"*.
- **Reality:** `AgentAuditLog` is append-only with **no automated purge**
  (`backend/models.py:596-629`) — there is no 90-day rolling deletion in code. The two
  statements also conflict (append-only ≠ 90-day rolling).
- **Proposed (interim):** reconcile to reality — *"The AI-action audit log is append-only
  and retained for the life of the account; it is not auto-purged."* If a 90-day rolling
  window is genuinely desired, implement a purge job first (Track B), then document it.
- **Note:** distinguish the *AI-action audit log* (append-only, `AgentAuditLog`) from
  general *access/system logs* (which may legitimately roll). If DPA §04's "90 days" refers
  to the latter, split the row so the two are not conflated.

---

## Part 2 — Additions (real controls the docs omit)

### R-07 · P2 · LAI-SEC-001 §06 (OWASP — Known Vulnerabilities) — add SAST
- **Current:** *"Automated dependency scanning (pip-audit) in CI on every change"*.
- **Addition:** *"…plus static application security testing (Bandit SAST) in CI on every
  change — blocking at medium+ severity and currently clean"*
  (`.github/workflows/ci.yml:80-102`). This is a real control the pack does not mention.

### R-08 · P3 · LAI-SEC-001 §08 (Penetration Testing) — reflect actual CI controls
- **Current:** describes automated dependency scanning + IDOR suite, and external pen
  testing "available on request."
- **Addition:** also cite Bandit SAST as an ongoing automated control. Ensure any future
  "Penetration Testing Summary" (roadmap Phase 7) does **not** imply an external pen test
  was performed unless one actually was — state clearly whether the summary covers
  automated controls only.

### R-09 · P3 · LAI-SEC-001 §02 / throughout — SOC 2 / ISO 27001 clarification
- **Current:** *"All infrastructure providers maintain SOC 2 Type II certification and ISO
  27001 compliance."*
- **Risk:** a skim-reader infers Leviii AI itself is certified.
- **Addition:** one clarifying line — *"These certifications are held by our infrastructure
  providers (Neon, Vercel, Railway, Sentry). Leviii AI Technologies is not itself SOC 2 or
  ISO 27001 certified at this time; our controls are documented and evidence-backed in the
  Control Evidence Matrix."* Honesty here is a strength in due diligence, not a weakness.

---

## Part 3 — Credibility & consistency (P3)

### R-10 · Contact address (decision: keep the single inbox)
- **Decision (2026-07-11):** the client contact across all documents is
  `leviiiaikenya@gmail.com`. This is the address to use in the pack today.
- **Optional future improvement:** if/when a custom domain is set up, role-based aliases
  (e.g. security@ / privacy@ / support@) forwarding to the same inbox would read as more
  established to enterprise buyers — optional, not required.

### R-11 · "Reviewed quarterly" cadence
- **Current:** LAI-SEC-001 exec summary: *"All controls are maintained continuously and
  reviewed quarterly."* Similar cadence claims elsewhere (BCP next-review Sep 2026).
- **Reality:** a v1.0 pack dated June 2026 cannot yet evidence a completed quarterly cycle.
- **Proposed:** *"Controls are maintained continuously and will be reviewed on a quarterly
  cadence; completed reviews are recorded in each document's revision history."* Then
  actually populate revision history as reviews happen (see R-12).

### R-12 · Document metadata standard (roadmap Phase 11)
Every document in the pack should carry the same metadata. Apply this **header** block
under each title and this **footer** table at the end.

**Header (under the title):**

| | |
|---|---|
| **Reference** | LAI-XXX-001 |
| **Version** | 1.0 |
| **Classification** | Public / Confidential / Internal |
| **Owner** | *(named role — e.g. Engineering, Legal, Data Protection)* |
| **Last Updated** | YYYY-MM-DD |
| **Contact** | *(role-based address per R-10)* |

**Footer — Revision history:**

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-06-?? | *(owner)* | Initial publication |

**Docs currently missing an `Owner` and/or `Revision history`:** all 12
(SEC, SLA, DPA, PP, AUP, BCP, TOS, SUB, AI, COO, BILL, IRP, KRA). Suggested owners —
SEC/IRP → Engineering; DPA/PP/COO/SUB → Data Protection; SLA/BILL/TOS/AUP → Legal;
BCP → Engineering; AI → Engineering; KRA → Legal/Finance.

---

## Application checklist

- [ ] R-01, R-02, R-06 applied (P1/P2 accuracy — interim wording) before the pack is shared.
- [ ] R-03, R-04, R-05 applied (P2 precision).
- [ ] R-07, R-08, R-09 applied (additions + SOC2 clarification).
- [ ] R-10 role-based addresses provisioned and swapped in.
- [ ] R-11, R-12 metadata + cadence wording applied to all 12 docs.
- [x] Track B1/B2 shipped — R-01 uses accurate-today wording (RBAC coverage expanding),
      R-02 restores the strong claim; Control Evidence Matrix statuses moved to Production.

## Revision history

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-07-11 | Engineering | Initial redline set from code audit |
| 1.1 | 2026-07-11 | Engineering | R-01/R-02 updated after Track B1/B2 shipped |
