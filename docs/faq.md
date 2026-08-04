# Leviii AI — Frequently Asked Questions

| | |
|---|---|
| **Reference** | LAI-FAQ-001 |
| **Classification** | Public |
| **Audience** | Restaurant owners, prospects, procurement |
| **Version** | 1.0 |
| **Last Updated** | 2026-07-11 |
| **Owner** | Leviii AI Technologies |
| **Contact** | leviiiaikenya@gmail.com |

Answers to the questions we get most. For the deep versions see the
[Technical Trust Center](trust/trust-center-technical.md) and
[Control Evidence Matrix](trust/control-evidence-matrix.md).

## General

**What is Leviii AI?**
A web-based restaurant operating system: POS, kitchen display, inventory, reservations,
financial intelligence, WhatsApp owner control, and M-Pesa payments.

**What do I need to run it?**
Any modern phone, tablet, or computer with a stable internet connection (10 Mbps+
recommended). Nothing to install.

**What happens if my internet or the app goes down?**
There's a paper fallback so service never stops, and we help you enter those orders
afterward. Data is backed up continuously and can be restored to a point in time. Recovery
targets are in the SLA/BCP.

**Can I get my data out?**
Yes — CSV export of orders and customers any time (admin). If you leave, we export and then
delete your data (SLA §08).

**How am I billed?**
Monthly subscription in advance + one-time setup fee; M-Pesa or bank transfer. Details in the
Billing Policy (LAI-BILL-001).

## Security

**Are my passwords safe?**
They're hashed with Argon2id (irreversible) and never stored or logged in plain text.

**Can another restaurant see my data?**
No. Every record is scoped to your restaurant/tenant, enforced at the query layer, and we run
an automated cross-tenant (IDOR) test on every code change.

**How do you stop someone brute-forcing my login?**
Two layers: per-IP rate limiting (10/min → blocked) and per-account lockout (5 failed
attempts → 15-minute lock). Both are tested.

**What if a device is lost or a token leaks?**
"Log out everywhere" (`/logout-all`) instantly invalidates every existing session.

**Is data encrypted?**
In transit (HTTPS/TLS) and at rest (AES-256, managed by our database provider Neon).

**Are you SOC 2 / ISO 27001 certified?**
Our infrastructure providers (Neon, Vercel, Railway, Sentry) are. Leviii AI itself is not yet
certified — our controls are documented and evidence-backed instead (see the Control Evidence
Matrix), and we're transparent about that.

**Do you run security testing?**
On every code change: dependency vulnerability scanning (pip-audit), static analysis (Bandit),
and the cross-tenant isolation suite — all blocking. External penetration testing is available
to enterprise clients on request.

**How do I report a vulnerability?**
Email leviiiaikenya@gmail.com — acknowledged within 24 hours (Vulnerability Disclosure Policy).

## AI

**Does the AI make decisions on its own?**
No. It's advisory. Anything with real impact (like a price change) is only a suggestion until
you approve it. Every AI action that changes data is logged (what, why, who approved).

**Is my data used to train AI models?**
No — not ours, and our AI provider is under terms that don't train on your data.

**Which "AI" actually uses a language model?**
Two things: free-text WhatsApp chat, and the short plain-language summaries shown next to your
analytics (pricing, profit, menu, ROI, marketing). In both cases the language model **never
does the math** — the analytics engines compute every figure deterministically, and the model
only interprets them. Any number it writes that isn't in the computed data is automatically
redacted before you see it. Structured commands (SALES, STOCK, APPROVE…) are handled by plain
code and never touch the model.

**Can the AI be tricked (prompt injection)?**
The language model's output is advisory and owner-reviewed and it can't take actions on its
own. It only ever sees free-text WhatsApp messages or a server-built numeric payload (never
raw untrusted text on the analytics path), and figures it can't back are redacted. See the
[Threat Model](security/threat-model.md).

## Reliability

**What uptime do you commit to?**
99.5% for core POS/KDS/API/dashboard; 99.0% for AI and WhatsApp (SLA §03), with service
credits if missed.

**How fast do you respond to problems?**
SEV-1 (POS down during service): a 15-minute response target and 2-hour resolution target
during support hours, reached on a direct WhatsApp line. Full severity table in the SLA.

Being straight about detection: automated uptime alerting is being rolled out, so outside
continuous coverage an incident may be reported by you before it is detected by us. The
response clock starts when we are notified. *(Adopts option (b) from
`docs/sales/legal-reconciliation.md` E1 — do not quote fixed 15-min / 24-7 / "automatic
alerting" numbers as committed until an external monitor is actually polling the health
endpoints.)*

## Still have questions?
leviiiaikenya@gmail.com

## Revision history

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-11 | Initial combined FAQ (general + security + AI + reliability) |
