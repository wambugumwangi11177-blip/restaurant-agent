# Your Data, Your Restaurant — Trust Overview

| | |
|---|---|
| **Reference** | LAI-TRUST-002 |
| **Classification** | Public |
| **Audience** | Restaurant owners and managers |
| **Version** | 1.2 |
| **Last Updated** | 2026-07-11 |
| **Owner** | Leviii AI Technologies |
| **Contact** | leviiiaikenya@gmail.com |

This is the plain-language version of how Leviii AI protects your restaurant. No jargon —
just straight answers to the questions owners actually ask. If you want the deep technical
version (for your IT person, an auditor, or an investor), ask us for the **Technical Trust
Center**.

---

## What does Leviii AI actually do for me?

It runs the day-to-day of your restaurant from any phone, tablet, or computer:

- Takes and tracks orders (POS) and sends them to the kitchen screen (KDS).
- Keeps an eye on your stock and warns you before you run out.
- Manages table bookings.
- Shows you what's making money and what isn't.
- Lets you run the restaurant by WhatsApp — ask for today's sales, approve a price change,
  check stock.
- Takes M-Pesa payments.

## Is my data safe?

Yes — and here's what that means in practice:

- **Your passwords are never stored as text.** They're scrambled with a modern method
  (Argon2) that can't be reversed, even by us.
- **Everything travels encrypted.** The connection between your device and Leviii AI is
  locked (HTTPS), the same technology your bank uses.
- **Your data is encrypted where it's stored**, by our database provider (Neon).
- **Nobody can guess their way into your account.** After 5 wrong password tries, the
  account locks for 15 minutes, and we limit how fast anyone can attempt logins at all.
- **If a device is lost or stolen,** you can log out *everywhere* at once — every existing
  session stops working instantly.

## Who can see my restaurant's data?

- **Only you and your team.** One restaurant can never see another restaurant's data — the
  system separates every business completely, and we test this automatically on every single
  update to make sure it stays true.
- **We never sell your data.** Not to anyone, for any reason.
- **We never use your data to train AI models** — not ours, and our AI provider is under
  terms that don't train on your information either.
- **Our engineers** can access the system only for support and maintenance, through
  accounts protected by two-factor login.

## What happens if something goes down?

- Your data is **backed up continuously**, and we can rewind the database to any point in
  the last several days if we ever need to.
- If the system has a problem, our monitoring usually catches it within minutes — often
  before you'd notice.
- We have a written recovery plan and clear time targets for getting each part back online
  (see our Service Level Agreement).
- If the internet or the app is ever completely unavailable, we give you a simple paper
  fallback so service never stops, and we help you enter those orders afterward.

## Does the AI do things on its own?

**No — not for anything that matters.** This is important:

- Most of the "AI" is just smart math on *your own* numbers — sales trends, stock forecasts.
  It doesn't make things up, and it does **all** the calculating.
- A language model is used in only two ways, and it **never does the math**: (1) free-text
  WhatsApp chat, and (2) writing the short plain-English summaries you see next to your
  numbers. Even then it can only repeat figures the system already worked out — if it ever
  writes a number it can't back up, we automatically hide it before you see it. Simple
  commands (like "SALES" or "APPROVE") don't go anywhere near a language model.
- **Nothing with real consequences happens without you saying yes.** A price change is only
  a *suggestion* until you approve it. Every action the AI takes is written into a permanent
  log — what it did, why, and who approved it.

## If something goes wrong, what do you promise?

- If there's ever a security incident affecting your data, we tell you — within 72 hours of
  confirming it — what happened, what was affected, and what we did about it.
- We have set response times for problems, from "the POS is down during service" (fastest)
  to general questions. These are in your Service Level Agreement.
- You can export all your data any time, and if you ever leave, we delete it.

## Straight talk: what we're still improving

We'd rather tell you than have you find out. Here's where we are:

- **Password strength rules at sign-up** — done. New passwords must be at least 8
  characters and mix letters and numbers.
- **Staff-vs-owner permission levels** — the sensitive owner-only actions (exporting or
  erasing customer data, viewing AI/financial usage, editing your restaurant profile) are
  now locked to owner/admin accounts. We're extending these finer-grained limits across the
  rest of the app so staff accounts are cleanly restricted to POS and Kitchen Display.

Neither affects the separation between different restaurants or the safety of your data —
they're about controls *inside* your own account.

---

## Want more detail?

- **Technical readers / auditors:** ask us for the **Technical Trust Center**
  (LAI-TRUST-001) and the **Control Evidence Matrix**.
- **Questions, privacy, or security:** leviiiaikenya@gmail.com

## Revision history

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-11 | Initial client trust overview |
| 1.1 | 2026-07-11 | Password rules shipped; staff/owner permissions now enforced on sensitive actions |
| 1.2 | 2026-07-11 | Clarified the AI section: the language model also writes plain-English summaries but never does the math, and unbacked numbers are auto-hidden |
