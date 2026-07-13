# Legal Pack Reconciliation & Handover Map (INTERNAL)

> Compares the two on-disk doc sets against the current codebase, lists the fixes to apply before hand-over, and maps every document to its page range and recipient. Verified 2026-07-12 against `backend/` source.

Two doc sets exist:
- **`~/Downloads/LeviiAI_Legal_Documents.pdf`** — 44-page legal/security pack, **June 2026 v1.0** (the oldest set; predates the July feature wave).
- **`~/Downloads/Leviii-AI-Docs/`** — 13 separate PDFs, **Jul 11** (export of the repo `docs/`).

---

## Part 1 — Fixes to apply before handover

### 🔴 E1 — SLA/BCP over-commits on monitoring you haven't wired (HIGHEST RISK)
`LAI-SLA-001` (pp. 6–10) and `LAI-BCP-001` (pp. 24–28) promise 15-min SEV-1 response, 24/7 emergency cover, "continuous uptime monitoring active," "SEV-1 incidents trigger automatic engineering alerts," 2–5 min detection, and 15-min RTO — **with automatic SLA credits.** Code check: **no uptime monitoring, alerting or paging is wired** (only a Prometheus `/metrics` endpoint, which exposes numbers but pages no one). This is a binding, credit-backed promise you can't currently evidence.

**Pick one before the SLA leaves the building:**
- **(a) Wire it first (recommended).** Add an external uptime monitor (UptimeRobot / Better Stack) hitting the API health route, with alerts routed to WhatsApp/email. ~1 hour. Makes the whole SLA honest as written.
- **(b) Soften the SLA** to what you can honor today. Suggested redline for SLA §04 "Automated Monitoring":
  > "Uptime monitoring is in place on the API and dashboard; service-critical (SEV-1) incidents are escalated to the engineering team as quickly as possible during and outside support hours. Automated real-time alerting is being rolled out; until then, incident detection may be manual outside continuous coverage."
  And soften the SEV-1 numbers from fixed 15-min/2-hour to "target" figures during support hours.
- **(c) Gate the aggressive SLA** to a top tier you can actually staff, and offer enterprises a realistic tier now.

**Until resolved: HOLD SLA-001 and BCP-001** — do not hand them over.

### 🟠 E2 — AI Transparency Statement is now factually inaccurate
`LAI-AI-001` (pp. 34–35) says *"Only that [WhatsApp] free-text path sends content to the language model."* **False now:** `/ai/pricing`, `/ai/profit` and `/ai/explain` attach a Groq-generated narrative (PII-scrubbed + grounding-verified, but content is sent). A reviewer comparing doc to app catches this.

**Ready-to-paste replacement for LAI-AI-001 §02, item 2 ("LANGUAGE MODEL"):**
> **2. LANGUAGE MODEL (optional, narration only).** A third-party large language model (currently Groq) is used in two places: (a) the WhatsApp Brain's free-text handler, and (b) an optional narrative layer that explains the deterministic analytics in plain language. In both cases the content sent to the model is PII-scrubbed first, and every figure the model returns is grounding-checked against the computed numbers — anything that doesn't trace to a real figure is redacted. Structured commands and **all numeric computation never touch the language model.**

Also update Groq's "purpose" line in `LAI-SUB-001` (pp. 32–33) and DPA §05 (p. 14) from "free-text WhatsApp replies" → **"free-text WhatsApp replies and AI narration of analytics (PII-scrubbed prompt content only; no training on submitted data)."**

*(Bonus: this reads as a deeper, safer AI story — an upsell, not just a correction.)*

### 🟡 E3 — Object storage: conditional sub-processor / residency gap
Storage defaults to `local` (`STORAGE_BACKEND=local`), so today's DPA residency claim ("primary storage: Neon US East; data never stored outside the US/Kenya chain," SEC p.1 / DPA) **still holds.** But setting `STORAGE_BACKEND=s3` adds an **unlisted sub-processor** (S3/R2) and a new at-rest location.
**Action:** Keep S3 **off** in production for now. Before ever enabling it, add the S3/R2 provider to `LAI-SUB-001` + DPA §05 and re-check the residency claim against the bucket region (give clients the 30-day sub-processor notice the docs promise).

### E4 — Undersell (leave legal conservative; carried by the brochure instead)
The pack never mentions shipped **TOTP MFA** or the agentic/enterprise layer. Understating AI is the *safe* side for a legal doc — leave it. The new **brochure** carries full capability. Optional squeaky-clean touch: add one line to Privacy Policy (p.17) "Automatic data" noting **self-hosted usage analytics** (the "no third-party analytics" claim stays true — the new analytics is self-hosted, not third-party).

### What's solid — hand over with confidence
SEC-001 encryption/Argon2id/brute-force/OWASP table; DPA data categories & subject rights; AUP; Cookie Policy; TOS; Billing; KRA note; Privacy Policy. All consistent with the code. The **advisory-only / human-in-the-loop / append-only audit log** framing matches reality exactly — it's your strongest trust story.

---

## Part 2 — Handover map (page numbers + who receives each)

### Legal pack `LeviiAI_Legal_Documents.pdf` (44 pages) — page ranges
| Document | Ref | Pages | Recipient | When |
|---|---|---|---|---|
| Security Architecture Overview | LAI-SEC-001 | **1–5** | Their IT / security | On request (NDA) |
| Service Level Agreement | LAI-SLA-001 | **6–10** | Owner + legal/procurement | **HOLD — fix E1 first** |
| Data Processing Agreement | LAI-DPA-001 | **11–15** | Legal / DPO | At contracting |
| Privacy Policy | LAI-PP-001 | **16–20** | Owner (public) | Freely |
| Acceptable Use Policy | LAI-AUP-001 | **21–23** | Owner / legal | At contracting |
| Business Continuity Plan | LAI-BCP-001 | **24–28** | Their IT | **HOLD — fix E1 first** |
| Terms of Service | LAI-TOS-001 | **29–31** | Owner / procurement | At contracting |
| Sub-Processor List | LAI-SUB-001 | **32–33** | Legal / IT (public) | Freely (keep S3 off — E3) |
| AI Transparency Statement | LAI-AI-001 | **34–35** | Owner + IT (public) | **After E2 fix** |
| Cookie Policy | LAI-COO-001 | **36–37** | Owner (public) | Freely |
| Billing & Refund Policy | LAI-BILL-001 | **38–39** | Owner / finance | At contracting |
| Incident Response Plan | LAI-IRP-001 | **40–42** | Their IT / security | On request (NDA) |
| Tax Record Integrity (KRA/eTIMS) | LAI-KRA-001 | **43–44** | Owner / their accountant | Freely |

### `Leviii-AI-Docs/` (13 separate PDFs) — recipient
| File | Recipient | When |
|---|---|---|
| 01-Trust-Overview-Client | Owner / CEO | Freely (Tier-1 trust) |
| 02-Trust-Center-Technical | Their IT / auditors | On request (NDA) |
| 03-Control-Evidence-Matrix | Their IT / auditors | On request (NDA) |
| 04-Architecture | Their IT | On request |
| 05-Engineering-Standards | Their IT | On request |
| 06-Operations-and-Reliability | Their IT | On request (MTTR/RTO marked TBD) |
| 07-Threat-Model-and-Risk-Register | Their security team | On request (NDA) |
| 08-AI-Governance | Owner + IT | Freely |
| 09-Compliance-Matrix | Legal / IT | Freely |
| 10-FAQ | Owner / CEO | Freely (Tier-1) |
| 11-Tech-Debt-Register | **INTERNAL — never share** | — |
| 12-Legal-Doc-Redlines | **INTERNAL — never share** | — |
| 13-Documentation-Roadmap-Status | **INTERNAL — never share** | — |

### New collateral (this folder, `docs/sales/`) — recipient
| Document | File | Recipient | When |
|---|---|---|---|
| Product Brochure / Why-Leviii / ROI / Comparison / Implementation / Support | `leviii-sales-pack.html` | Owner / CEO | Lead the meeting; leave behind |
| Talk-track + demo script + caveats | `talk-track-internal.md` | **YOU only — internal** | Prep |
| This reconciliation & handover map | `legal-reconciliation.md` | **YOU only — internal** | Prep |

**Recipient shorthand:** *Owner/CEO* → outcomes-first collateral + public docs. *Their IT/security* → technical/trust docs, usually under NDA. *Internal-only* → never leaves your side.
