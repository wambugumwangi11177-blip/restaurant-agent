# Leviii AI — Technical Trust Center

| | |
|---|---|
| **Reference** | LAI-TRUST-001 |
| **Classification** | Confidential — shared under NDA |
| **Audience** | Enterprise buyers, investors, auditors, security engineers |
| **Version** | 1.2 |
| **Last Updated** | 2026-07-11 |
| **Owner** | Engineering (Leviii AI Technologies) |
| **Contact** | leviiiaikenya@gmail.com |

## How to read this document

This is the technical companion to the Leviii AI legal/security pack. It answers the six
questions a due-diligence reader needs to answer *without* a call, and every security claim
here traces to a specific control in the
[Control Evidence Matrix](control-evidence-matrix.md) — which in turn cites the exact file,
line, or CI job that implements it.

Where a control is not yet fully enforced in code, this document says so plainly and links
to the tracked work. We would rather under-claim and cite evidence than over-claim.

- **Purpose:** give a technical reader a complete, honest picture of the platform.
- **Scope:** the production Leviii AI Restaurant Operating System (frontend, API, database,
  AI layer, integrations).
- **Assumptions:** reader is technical; provider certifications (Neon/Vercel/Railway/Sentry
  SOC 2 Type II) are accepted at the infrastructure layer.
- **Limitations:** Leviii AI is not itself SOC 2 / ISO 27001 certified; see Q3.

---

## Q1 — What does the system do?

Leviii AI is a multi-tenant SaaS restaurant operating system delivered as a web app. Core
capabilities:

- **POS + Kitchen Display System (KDS)** — order capture and kitchen routing.
- **Inventory** — stock levels, movements, and statistical reorder forecasting.
- **Reservations** — bookings against physical tables.
- **Revenue / Profit / Pricing intelligence** — deterministic analytics over the tenant's
  own operational data.
- **WhatsApp Brain** — owner interaction over WhatsApp; structured commands handled
  deterministically, free-text handled by an LLM.
- **Grounded reasoning layer** — plain-language narration over the deterministic analytics
  (pricing, profit, menu, ROI, marketing). The LLM interprets figures the engines already
  computed; it performs no arithmetic and any number it cannot back is auto-redacted.
- **M-Pesa payments** — mobile-money capture via Safaricom Daraja.

Data categories, retention, and data-subject rights are governed by the DPA (LAI-DPA-001)
and Privacy Policy (LAI-PP-001).

## Q2 — How is it built?

**Topology.**

```
        Customer / Owner devices
                 │  HTTPS
                 ▼
   ┌───────────────────────────┐
   │ Frontend  (Next.js/Vercel)│  Global CDN, TLS at edge
   └───────────────────────────┘
                 │  HTTPS  (JSON, Bearer JWT)
                 ▼
   ┌───────────────────────────┐
   │ API  (FastAPI / Railway)  │  TLS terminated at edge
   │  • security-headers mw    │
   │  • SlowAPI rate limiting  │
   │  • JWT auth + tenant scope│
   │  • /api/v1 routers        │
   └───────────────────────────┘
        │            │            │
        ▼            ▼            ▼
   ┌─────────┐  ┌─────────┐  ┌──────────────┐
   │  Neon   │  │  LLM    │  │ Twilio /     │
   │Postgres │  │free-txt+│  │ M-Pesa Daraja│
   │(US East)│  │grounded │  │ (per-tenant) │
   └─────────┘  │narration│  └──────────────┘
                └─────────┘
   Sentry ← error + performance monitoring (all app tiers)
```

- **Frontend:** Next.js on Vercel (global CDN, output-encoded by default).
- **API:** FastAPI on Railway; TLS terminated at the edge. Middleware order matters —
  security headers and SlowAPI rate limiting wrap every request; authenticated routes
  depend on `get_current_user`.
- **Database:** Neon PostgreSQL (US East), accessed exclusively through the SQLAlchemy ORM.
- **Versioning:** all routers mounted under `/api/v1` (evidence matrix §7).
- **Source of truth:** GitHub; CI (`.github/workflows/ci.yml`) gates every change.

## Q3 — How is it secured?

Every item below is evidence-backed in the matrix. Summary by domain:

- **Authentication:** Argon2id password hashing; a registration password policy (min-8,
  letters + digits); JWT (HS256, 8-hour expiry); stateless
  session **revocation** via a `token_version` claim (`/logout-all` invalidates every
  outstanding token). *(Matrix §1.)*
- **Brute-force defense (two independent layers):** per-IP SlowAPI rate limiting on login
  (10/min → HTTP 429) and per-account lockout (5 failed attempts → 15-minute lock, checked
  before password verification so locked accounts get no timing signal). Both covered by an
  automated test suite. *(Matrix §1.)*
- **Authorization / tenancy:** every operational record binds to a restaurant that resolves
  to exactly one tenant; queries are scoped by `restaurant_id`; cross-tenant access by ID
  (IDOR) returns 404 and is covered by an automated isolation suite that runs in CI.
  *(Matrix §2.)*
- **Injection:** SQLAlchemy ORM parameterization (no raw string SQL on user input); typed
  Pydantic request-body validation. *(Matrix §3.)*
- **Transport & secrets:** TLS at the edge; HSTS on every response; secrets from environment
  only, with a fail-closed startup guard that refuses to boot in production without
  `SECRET_KEY`. At-rest AES-256 is provider-managed by Neon. *(Matrix §4, §7.)*
- **HTTP headers:** `nosniff`, `X-Frame-Options: DENY`, HSTS (2-year), `Referrer-Policy`,
  `Permissions-Policy` — on all responses. *(Matrix §5.)*
- **Supply chain / CI:** `pip-audit` (blocking) and **Bandit SAST** (blocking, clean) on
  every push/PR; 31-file pytest suite; frontend build + typecheck + npm audit. *(Matrix
  §6.)*

**Honest limitations (tracked in the matrix):**
1. **RBAC is enforced, coverage is expanding.** A `require_role` dependency now enforces
   roles on admin-sensitive routes (data export/erasure, AI observability, restaurant
   profile), covered by tests. It is not yet applied to *every* operational route, so the
   full "STAFF = POS/KDS only" surface is still being completed.
2. Request schemas do not yet reject unexpected fields (`extra="forbid"`).
3. The AI-action audit log is append-only with no automated purge (see the audit-retention
   note; DPA wording is being reconciled).
4. Within-tenant multi-restaurant scoping resolves to the first restaurant (not a
   cross-tenant issue; fix tracked).
5. **Certification:** Leviii AI is not itself SOC 2 / ISO 27001 certified; those
   certifications are held by our infrastructure sub-processors. Our own controls are
   documented and evidence-backed here rather than third-party attested.

*(Shipped 2026-07-11: RBAC enforcement mechanism and registration password-complexity
validation — both now Production in the Control Evidence Matrix.)*

### Key flows

**Authentication flow.** Login → lockout check → Argon2 password verify → JWT minted with
`sub` + `ver` (current `token_version`). Every protected request decodes the JWT, loads the
user, and rejects the token if `ver` ≠ the user's `token_version`. `/logout-all` bumps
`token_version`, instantly revoking all prior tokens.

**Tenant-isolation flow.** Request → `get_current_user` → resolve the caller's restaurant
from their tenant → every query filtered by `restaurant_id`. A request for another tenant's
record ID matches nothing and returns 404. The IDOR test suite asserts this for orders,
reservations, and inventory.

**Payment flow.** Order → M-Pesa STK push via Safaricom Daraja → asynchronous callback to a
webhook (signature/token-validated) → payment recorded referencing the M-Pesa transaction
(no card data stored). M-Pesa is enabled per tenant.

**AI request path.** The LLM is used in two bounded roles and computes nothing in either.
(1) *WhatsApp* — owner message → deterministic command router; structured commands (SALES,
STOCK, APPROVE, REJECT, PROMO…) are handled *without* any LLM, and only unmatched free-text is
sent to the LLM. (2) *Grounded narration* — the deterministic analytics engines produce every
figure, and the LLM only turns that already-computed payload into plain-language judgment;
a grounding verifier redacts any number not present in the payload before it reaches the owner.
Data-changing actions require explicit approval and are written to an append-only audit log
recording what changed, why, and who approved. The LLM provider is configuration-driven (Groq
today; upgrades to Anthropic Claude by task tier via a single env change for production
customers, no code change).

## Q4 — How is it operated & maintained?

- **CI/CD:** GitHub is the source of truth; Railway and Vercel deploy from it with one-click
  rollback. Every change passes `pytest`, `pip-audit`, Bandit SAST, and frontend
  build/typecheck.
- **Startup safety:** the API refuses to start in production with missing critical config
  (fail-closed guard).
- **Monitoring:** Sentry for errors + performance (20% trace sample). An in-app AI
  observability endpoint (`GET /api/v1/ai/usage`) exposes LLM token spend, per-agent latency
  (p50/p95), success rate, and grounding trust rate. Health endpoints `GET /health`,
  `/health/db` and `/health/notifications` are available as external monitor targets.
  **External uptime polling and paging are not yet wired** — incident detection is
  currently manual (see [Operations & Reliability §1](../operations-and-reliability.md)).
- **Alert delivery:** operational alerts to the restaurant owner are sent over WhatsApp/SMS.
  That path depends on a configured messaging provider, so `GET /health/notifications`
  reports whether it can currently deliver at all rather than letting it fail silently.
- **Backups & recovery:** Neon WAL + daily snapshots with point-in-time restore; procedures
  in `backend/DISASTER_RECOVERY.md`. RTO/RPO targets are in the BCP (LAI-BCP-001).
- **Incident response:** severity model, containment, and notification timelines in the IRP
  (LAI-IRP-001) and DPA §06 (72-hour client notification on confirmed breach).

## Q5 — How do you know the controls actually work?

This is what the [Control Evidence Matrix](control-evidence-matrix.md) exists for. For every
control it records implementation, verification method, evidence (file:line or CI job), and
last-verified date. Independent verification a reader can rely on:

- **Automated tests** run on every change — including the cross-tenant IDOR suite and the
  auth brute-force tests (lockout + rate-limit both assert HTTP 429).
- **CI gates** — `pip-audit` and Bandit SAST are *blocking*, so a new dependency CVE or a
  new medium+ static-analysis finding fails the build.
- **Manual audit** — the matrix's "Last verified" column dates the most recent line-by-line
  code review of each claim.

Where evidence does not exist, the matrix marks the control **Planned**, not Production.

## Q6 — How does the platform evolve?

- **Version control & history:** every document here is versioned Markdown in the repository;
  `git` history is the authoritative change record. Each doc carries a revision-history
  table.
- **Roadmap discipline:** aspirational items are marked as such (e.g. offline-first PWA,
  public status page, eTIMS integration) and are not presented as shipped.
- **This trust center is living:** as Track B controls ship, the matrix statuses move from
  Planned → Production and the corresponding legal-pack wording is restored (see
  [legal-doc-redlines.md](legal-doc-redlines.md)).

---

## References

- [Control Evidence Matrix](control-evidence-matrix.md) — LAI-EVID-001
- [Legal-Pack Redline Change-List](legal-doc-redlines.md) — LAI-REDLINE-001
- [Client Trust Overview](trust-center-client.md) — plain-language companion
- Legal pack: LAI-SEC-001, LAI-SLA-001, LAI-DPA-001, LAI-PP-001, LAI-AUP-001, LAI-BCP-001,
  LAI-TOS-001, LAI-SUB-001, LAI-AI-001, LAI-COO-001, LAI-BILL-001, LAI-IRP-001, LAI-KRA-001
- Runbook: `backend/DISASTER_RECOVERY.md`

## Revision history

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-07-11 | Engineering | Initial technical trust center, grounded in code audit |
| 1.1 | 2026-07-11 | Engineering | Updated limitations after RBAC + password-policy shipped (Track B1/B2) |
| 1.2 | 2026-07-11 | Engineering | AI request path corrected to two bounded LLM roles (free-text + grounded narration); documented grounding redaction and Groq→Anthropic upgrade path |
