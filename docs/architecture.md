# Leviii AI — System Architecture

| | |
|---|---|
| **Reference** | LAI-ARCH-001 |
| **Classification** | Confidential — shared under NDA |
| **Audience** | Engineers, auditors, technical due diligence |
| **Version** | 1.1 |
| **Last Updated** | 2026-07-11 |
| **Owner** | Engineering (Leviii AI Technologies) |
| **Contact** | leviiiaikenya@gmail.com |

## Purpose, scope, assumptions

- **Purpose:** describe how the platform is built, end to end, so a technical reader can
  reason about its behavior and security without reading the source.
- **Scope:** the production Leviii AI Restaurant Operating System — frontend, API, database,
  AI layer, and third-party integrations.
- **Assumptions:** provider-managed layers (TLS termination, at-rest encryption, CDN) are
  operated by Vercel/Railway/Neon under their SOC 2 Type II programs.
- **Grounding:** file references point at the live `backend/` tree and are cross-checked in
  the [Control Evidence Matrix](trust/control-evidence-matrix.md). The abandoned
  `restaurant-agent/` duplicate tree is git-ignored and out of scope.

---

## 1. Production architecture (topology)

```
                      Customer / Owner devices (browser, WhatsApp)
                                   │  HTTPS
                                   ▼
                    ┌───────────────────────────────┐
                    │  Frontend — Next.js on Vercel  │  Global CDN · TLS at edge
                    │  output-encoded React (XSS)    │
                    └───────────────────────────────┘
                                   │  HTTPS · JSON · Bearer JWT
                                   ▼
        ┌──────────────────────────────────────────────────────────┐
        │  API — FastAPI on Railway  (TLS terminated at edge)        │
        │  middleware:  SecurityHeaders → SlowAPI rate-limit         │
        │  auth:        get_current_user (JWT + token_version)       │
        │  authZ:       require_role(...) on admin routes            │
        │  routing:     /api/v1/* routers                            │
        │  startup:     fail-closed config guard                     │
        └──────────────────────────────────────────────────────────┘
             │                    │                       │
             ▼                    ▼                       ▼
   ┌──────────────────┐  ┌─────────────────┐   ┌──────────────────────┐
   │ Neon PostgreSQL  │  │ LLM provider     │   │ Twilio (WhatsApp)    │
   │ (US East)        │  │ WhatsApp free-txt│   │ Safaricom M-Pesa     │
   │ SQLAlchemy ORM   │  │ + grounded narr. │   │ Daraja (per-tenant)  │
   │ Alembic migr.    │  │ Groq → Anthropic │   └──────────────────────┘
   └──────────────────┘  └─────────────────┘
        Sentry ← errors + performance traces (all tiers)
```

**Layer responsibilities**

| Layer | Tech | Responsibility |
|---|---|---|
| Frontend | Next.js / Vercel | UI, output encoding, calls the API with a Bearer JWT |
| API | FastAPI / Railway | Business logic, auth, tenant scoping, integrations |
| Database | Neon PostgreSQL | Durable state; accessed only via SQLAlchemy ORM |
| AI | Deterministic Python (analytics) + LLM (WhatsApp free-text & grounded narration; Groq today → Anthropic Claude on upgrade) | Advisory decision-support; LLM never computes |
| Payments | Safaricom M-Pesa Daraja | Mobile-money capture (per tenant) |
| Messaging | Twilio | WhatsApp send/receive (per tenant) |
| Monitoring | Sentry | Errors + performance |

---

## 2. Security architecture

Defense in depth, request-inward:

1. **Edge** — Vercel/Railway terminate TLS; HTTP is served over HTTPS at the platform layer.
2. **Response headers** — `SecurityHeadersMiddleware` sets `nosniff`, `X-Frame-Options:
   DENY`, HSTS (2 years), `Referrer-Policy`, `Permissions-Policy` on every response
   (`backend/middleware/security_headers.py`).
3. **Rate limiting** — SlowAPI per-IP limits (login 10/min, register 5/hour) → HTTP 429.
4. **Authentication** — JWT (HS256, 8h) with a `token_version` revocation claim
   (`backend/auth.py`).
5. **Authorization** — `require_role(...)` gates admin-sensitive routes; SUPERADMIN bypasses
   (`backend/auth.py`).
6. **Tenant isolation** — every query scoped by `restaurant_id` resolved from the caller's
   tenant (`backend/routers/deps.py`).
7. **Input** — SQLAlchemy ORM parameterization; typed Pydantic request bodies.
8. **Secrets** — environment only; fail-closed startup guard (`backend/startup_checks.py`).
9. **Data at rest** — AES-256, Neon-managed.

Full evidence per control: [Control Evidence Matrix](trust/control-evidence-matrix.md).

---

## 3. Authentication flow

```
POST /api/v1/auth/login {email, password}
   │
   ├─ locked_until in the future?  ── yes ─▶ 429 (no password check; no timing signal)
   │
   ├─ Argon2id verify(password)
   │     fail ─▶ failed_login_attempts++ ; if ≥5 set locked_until=+15min ─▶ 401
   │     ok   ─▶ reset counter, set last_login_at
   │
   └─ mint JWT { sub: email, ver: user.token_version, exp: +8h }  ─▶ 200 {access_token}

Every protected request:
   decode JWT → load user → reject if token.ver != user.token_version → inject current_user
```

- **Revocation:** `POST /api/v1/auth/logout-all` bumps `token_version`, instantly
  invalidating every previously-minted token (`backend/routers/auth.py`).
- **Registration** enforces a password policy (min-8, letters + digits) before hashing.

## 4. Authorization / tenant-isolation flow

```
Request + Bearer JWT
   │
   ├─ get_current_user → User (with tenant_id)
   │
   ├─ [admin routes] require_role(ADMIN): role∈{ADMIN} or SUPERADMIN else 403
   │
   ├─ resolve restaurant: Restaurant where tenant_id == user.tenant_id
   │
   └─ every query filtered by restaurant_id
         request for another tenant's record id ─▶ matches nothing ─▶ 404
```

Enforced and tested for orders, reservations, and inventory
(`backend/tests/test_tenant_isolation.py`). Admin gating tested in
`backend/tests/test_rbac.py`.

## 5. Payment flow (M-Pesa)

```
Order (unpaid) ─▶ STK push via Safaricom Daraja (backend/payments/mpesa_client.py)
                        │
   customer approves on phone
                        ▼
   async callback ─▶ POST webhook (backend/routers/webhooks.py)
                        │  signature/token validated (fail-closed if token unset in prod)
                        ▼
   payment recorded referencing the M-Pesa receipt/reference  (no card data stored)
                        │
                        └─ emits payment event ─▶ AI orchestrator (audit-logged)
```

M-Pesa is enabled per tenant; if not configured, no data is sent to Safaricom.

## 6. AI architecture

The platform uses an LLM in **two** places, and **never for arithmetic** (see
[AI Governance](ai-governance.md)). All numbers are computed by deterministic
Python; the LLM only interprets or converses.

```
(1) Owner WhatsApp message
   │
   ├─ deterministic command router (backend/ai/whatsapp/brain.py)
   │     SALES / STOCK / APPROVE / REJECT / PROMO ... ─▶ handled WITHOUT any LLM
   │
   └─ unmatched free-text ─▶ LLM (backend/ai/llm_client.py)
                                  │
                                  ▼
                          orchestrator → advisory reply

(2) Analytics payload (deterministic) ─▶ grounded reasoning layer
      pricing / profit / menu / roi / marketing / explain
      (backend/ai/reasoning/narrator.py)
                                  │
      LLM reads the already-computed numbers and writes plain-language
      judgment. It may only cite figures present in the payload; a grounding
      verifier (backend/ai/reasoning/grounding.py) redacts any unbacked number
      before it reaches the owner. Narration is optional (narrate=false skips it)
      and strictly additive — the deterministic numbers show with or without it.

   Data-changing actions (either path) require explicit approval and are written
   to an append-only AgentAuditLog (what changed, why, who approved).
```

The Revenue/Profit/Pricing/Inventory/KDS/Reservation "intelligence" engines are
**deterministic analytics** over the tenant's own data — same input → same output.
The LLM performs no calculation on top of them; it interprets the results. Both
LLM paths run on Groq today; the client is provider-agnostic and upgrades to
Anthropic Claude (Haiku/Sonnet/Opus by task tier) via a single env change for
production/paying customers (`backend/ai/llm_client.py`).

## 7. Database architecture

- **Engine:** Neon PostgreSQL, accessed only through SQLAlchemy ORM (`backend/models.py`,
  `backend/database.py`). No raw string SQL on user input.
- **Tenancy:** `Tenant 1─* Restaurant 1─* {Order, Reservation, InventoryItem, Table,
  MenuItem, ...}`. Every operational row carries `restaurant_id`.
- **Integrity:** CHECK constraints (non-negative money, positive quantities/party size),
  UNIQUE (restaurant_id, table_number), pervasive FKs/NOT NULL
  (`backend/models.py`, `backend/alembic/versions/016_add_integrity_constraints.py`).
- **Audit:** `AgentAuditLog` — append-only AI-action trail (`backend/models.py`).
- **Migrations:** Alembic, versioned `001`…`017` (`backend/alembic/versions/`).

## 8. Data-flow (personal data)

| Data | Entry | Store | Leaves to | Basis |
|---|---|---|---|---|
| Staff email + Argon2id hash | registration | Neon | — | account |
| Customer name/phone | order/reservation | Neon | Twilio (WhatsApp), M-Pesa (phone) — per feature | consent |
| Order/payment records | POS / M-Pesa | Neon | — (CSV export on admin request) | tax/ops |
| Free-text owner message | WhatsApp | transient | LLM provider (prompt only, no training) | feature |
| Deterministic analytics payload (for narration) | app-internal | transient | LLM provider (prompt only, no training; no raw customer text) | feature |

Erasure scrubs customer PII while retaining the financial transaction record
(`backend/routers/export.py::erase_customer`), per DPA §03.

## 9. Deployment architecture

```
GitHub (source of truth)
   │  push / PR → CI (.github/workflows/ci.yml): pytest · pip-audit · bandit · frontend build+typecheck
   ├─▶ Railway  → API  (deploy on merge; one-click rollback)
   └─▶ Vercel   → Frontend (deploy history; instant rollback)
Neon: managed Postgres, WAL + daily snapshots, point-in-time restore
```

See [Engineering Standards](engineering-standards.md) for the CI gates and release process,
and [Operations & Reliability](operations-and-reliability.md) for backup/restore and SLOs.

## References

- [Control Evidence Matrix](trust/control-evidence-matrix.md)
- [Engineering Standards](engineering-standards.md) · [Operations & Reliability](operations-and-reliability.md)
- [AI Governance](ai-governance.md) · [Threat Model](security/threat-model.md)
- Legal pack: LAI-SEC-001, LAI-DPA-001, LAI-BCP-001, LAI-AI-001

## Revision history

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-07-11 | Engineering | Initial architecture doc from code audit |
| 1.1 | 2026-07-11 | Engineering | §6 corrected to the two-path LLM model (WhatsApp free-text + grounded reasoning/narration layer); documented Groq→Anthropic Claude upgrade path; "LLM never computes" invariant made explicit |
