# Leviii — Cold Call Playbook

> **INTERNAL. Never send to a prospect.**
> Companion to `talk-track-internal.md` (demo script) and `leviii-sales-pack.html` (leave-behind).
> Every claim below is traceable to code. The honesty guardrails in the talk-track apply here in full.

---

## 0. The 60-second version (read this before your first dial)

1. **Your opener is permission, not pitch.** "Can I have 27 seconds?" — then actually stop talking.
2. **Your hook is the price leak**, not the AI. "Your till is charging less than your menu."
3. **Ask, don't tell.** The prospect must say the problem out loud before you say the product.
4. **Your only goal on the call is a 15-minute demo booked.** You are not closing a POS deal on a cold call.
5. **Never quote an SLA number.** Never promise the marketplace, menu-photo/vision, or Stripe.
6. **Dials are the job.** 40 dials → ~12 conversations → ~3 demos → ~1 pilot. Miss the dials, miss the month.

---

## 1. Why this product is unusually easy to cold call

Most software cold calls fail because the seller opens with a *category* ("we're a restaurant POS with AI"). Category openers get "we already have one."

Leviii has something rarer: **a specific, checkable, money-shaped accusation about the prospect's business that you can make before you know anything about them** — and be right most of the time.

That accusation is portion drift.

### The evidence (this is the whole pitch)

`backend/ai/profit/intelligence.py` → `_detect_portion_drift()` compares each menu item's **listed price** against the **average price actually captured at the till** over a 14-day window. If the gap exceeds 5%, it flags the item and extrapolates the monthly leak:

```python
drift_pct = ((item.price - avg_price) / max(item.price, 1)) * 100
if drift_pct > 5:
    monthly_leak = int((item.price - avg_price) * row.cnt * (30 / 14))
```

In plain English: **the menu says 850, the till rings 780, nobody wrote it down, and it happens 40 times a week.** Unauthorised discounts, staff "friend prices", mis-keyed items, quiet theft. Every restaurant owner in Nairobi suspects this is happening. Almost none can prove it. Leviii proves it in numbers, per dish, per month.

That is your cold call. Not "AI". Not "operating system". **"I can tell you, per dish, how much your till is undercharging you every month."**

### The rest of the evidence you're allowed to lean on

| Claim you can make | Where it lives in the code |
|---|---|
| "Every profit number is deterministic math on your data — the AI explains, it never invents the number." | `ai/decisions/ranking.py` — "No LLM, no randomness — the same set of decisions always ranks the same way" |
| "Recommendations are ranked by money, confidence, risk and effort — and I can show you the weights." | `ranking.py`: `W_IMPACT=0.45, W_CONFIDENCE=0.25, W_RISK=0.15, W_EASE=0.15`, referenced against KES 100,000/month |
| "We never add up our savings into one flattering number." | `ai/roi/savings.py` — three totals "deliberately never summed": hours saved, money captured, opportunities |
| "The only 'money we made you' figure counts recommendations *you approved*." | `savings.py` — `money_captured` counts only `PricingRecommendation.status == APPROVED` |
| "We flag any dish under 40% margin as critical, and food cost over 35%." | `profit/intelligence.py`: `HEALTHY_FOOD_COST_MAX=35.0`, `CRITICAL_MARGIN_FLOOR=40.0` |
| "We show you what delivery apps really cost you — 25% on Uber Eats and Glovo, 20% on Bolt Food." | `profit/intelligence.py`: `DELIVERY_COMMISSIONS` |
| "M-Pesa STK push, reconciled exactly once." | `backend/payments/` |
| "Live in four days." | Sales pack, onboarding timeline |

**The moat sentence**, when they ask why their POS vendor can't just add this:
> "Because the numbers are deterministic math on your real data — the AI only ranks and explains, it never guesses. That's what lets you trust it to touch pricing. Bolting a chatbot onto a POS doesn't get you that."

---

## 2. The ten teachers, and exactly what we take from each

Researched and compressed into what actually survives contact with a Nairobi restaurant owner at 10am on a Tuesday.

### 1. Andy Elliott — energy, tonality, and earning the right
**What he teaches:** "You want to ask for somebody's business, you got to earn the right to ask for it." Your voice is the first impression — confident, warm, unhurried. Practise by role-play, relentlessly, out loud.
**What we take:**
- **Smile before the dial.** It is audible. Owners in this market read confidence as competence.
- **Never ask for the deal before you've earned it.** On a cold call you have earned the right to ask for *15 minutes*, nothing more.
- **Role-play daily.** 20 minutes before dialling, run objections with a colleague. Untrained reps freeze on "we already have a POS"; trained reps enjoy it.
- **Pace and pause.** Say the leak number, then *shut up*. The silence does the selling.
**What we discard:** The hype-heavy, high-pressure register. It works on a car lot; it burns trust with a restaurant owner who's been sold bad software before.

### 2. Jeremy Miner (NEPQ) — neutral tone, question sequence
**What he teaches:** Neuro-Emotional Persuasion Questioning. Six stages: Connection → Situation → Problem Awareness → Solution Awareness → Consequence → Commitment. Curious-neutral tonality, never eager. The prospect persuades themselves.
**What we take:** *This is our primary call structure.* See §4. The single highest-value move: **problem-awareness questions** that surface a leak the owner hasn't quantified, followed by a **consequence question** that puts a number on the year.
**Key line we use:** "How are you currently figuring out which dishes actually make you money?" — then, whatever they say, "How's that been working out?"

### 3. Chris Voss — tactical empathy
**What he teaches:** Labels ("It sounds like…"), mirrors (repeat their last 3 words), the **accusation audit** (say their objection before they do), and **no-oriented questions** (people feel safe saying no).
**What we take:**
- **Accusation audit as our opener.** "You're going to hate this — I'm calling out of the blue and you've probably been pitched three POS systems this month." Disarms the reflex hang-up.
- **"Is now a ridiculous time to talk?"** — a no-oriented question. "No" means continue.
- **"How am I supposed to do that?"** for the price squeeze, instead of discounting.
- **Mirroring** to keep an owner talking when they give you a one-word answer.

### 4. Josh Braun — poke the bear, ditch the pitch
**What he teaches:** Permission-based opening, then a *neutral* question that makes the prospect question their status quo — without leading them. Zero pressure. "Ditch the pitch. Poke the bear."
**What we take:** Our poke, almost verbatim in structure:
> "Most restaurants I talk to in Nairobi find out at the end of the month that a few dishes were quietly sold below menu price — discounts, mis-keys, friend prices. How does that compare with what you see?"

Note the mechanics: it's a *comparison* question, not a leading one. It gives them room to say "that doesn't happen here" — and that answer is also useful, because it's usually wrong, and now they're curious.
**Also take:** the **tease** — "Would you be open to…" rather than "Can I book you for…".

### 5. Alex Hormozi — the value equation and risk reversal
**What he teaches:** Value = (Dream Outcome × Perceived Likelihood) ÷ (Time Delay × Effort & Sacrifice). Make the offer so good it feels stupid to say no.
**What we take:** Our offer is engineered against all four terms:
- **Dream outcome** ↑ — "know exactly which dishes make you money."
- **Perceived likelihood** ↑ — deterministic math, audit trail, we run it on *your* data before you commit.
- **Time delay** ↓ — **live in four days**, and the leak report lands in the first week.
- **Effort & sacrifice** ↓ — we import your menu, we train your staff, you approve with one tap.
- **Risk reversal** — the paid pilot (see §7). This is the single biggest conversion lever we have.

### 6. Grant Cardone — activity volume and follow-up
**What he teaches:** 10X action. Most sellers quit after one or two touches. Persistence and massive activity beat cleverness.
**What we take:** The dial minimum and the **follow-up cadence** (§8). Nobody buys a restaurant operating system on touch one. The pilot signatures come from touches four through seven.
**What we discard:** Pressure closing and "never take no". In a small, tight-knit market like Nairobi hospitality, a bullied prospect tells ten other owners.

### 7. Sandler — pain funnel, upfront contracts, disqualify early
**What he teaches:** Set an upfront contract (agree the agenda and outcome before you start). Ask pain questions in a funnel: surface → specifics → personal impact. Be willing to disqualify.
**What we take:**
- **Upfront contract at the top of the demo:** "15 minutes; I'll show you three things; at the end you tell me either 'not for us' or 'let's pilot' — both are fine answers."
- **Pain funnel** on the leak: "How long has that been happening?" → "What have you tried?" → "What did that cost you last year?" → "How does that land on you personally when the month closes short?"
- **Disqualify fast.** A 20-cover single-site café with no POS and no smartphone isn't our buyer today. Say so kindly and move on. Your time is the scarce resource.

### 8. The Challenger Sale — teach, tailor, take control
**What he teaches:** The best reps lead with **commercial insight** that reframes how the customer sees their own business, then tailor it, then confidently drive the process.
**What we take:** Our reframe, and it's a strong one:
> "A POS takes orders. It tells you what you *sold*. It cannot tell you what you *earned* — and it definitely can't tell you what it let walk out the door."
That's the teach. It reframes the entire category from "we have a POS already" to "our POS is not the thing that solves this."
**Take control:** always propose the specific slot. "Thursday 3pm or Friday 11am?" Never "let me know what works."

### 9. Jordan Belfort — the straight line and the three tens
**What he teaches:** Move from open to close along the shortest line. The prospect must be certain of three things: the product, you, and the company. Control the frame; loop back on objections.
**What we take:**
- **Certainty in the product** → the deterministic-math moat sentence.
- **Certainty in you** → know your numbers cold. Fumbling a margin question kills the deal.
- **Certainty in the company** → "Nairobi-based, we onboard you in person in four days" beats a foreign vendor with an email address.
- **Looping:** when an objection returns a second time, it's not the real objection. Go back to pain.
**What we discard:** the manufactured urgency and the hard tonality. We don't need it; the leak number is urgent on its own.

### 10. Jeb Blount — fanatical prospecting, objections are emotional
**What he teaches:** Most sellers fail not at closing but at *not talking to enough people*. Objections are emotional reflexes, not logical positions — expect them, don't take them personally.
**What we take:**
- **Pipeline math over mood.** Track dials, not feelings (§9).
- **The reflex rule:** the first "not interested" (within 5 seconds) is a *reflex*, not a decision. It arrives before they've heard anything. You get exactly one polite attempt to convert a reflex into a conversation — take it, then respect the second no.
- **Prospect in blocks.** Two uninterrupted 90-minute blocks beat a day of scattered dialling.

---

## 3. Who to call today (and when)

### Target list — best to worst for a first call

| Tier | Profile | Why |
|---|---|---|
| **A** | 2–8 branch Nairobi restaurant/café groups, KES 1.5M–6M/mo per site | Multi-branch is where the benchmarking screen and the chain-wide audit trail close deals. Highest ACV, fastest "yes" |
| **A** | Owner-operated single sites doing KES 3M+/mo, high delivery mix | Delivery commissions (25/25/20%) are eating them and they can feel it but not measure it |
| **B** | Hotel F&B and members' clubs | Longer cycle, but they have a finance person who *loves* the audit trail |
| **C** | Single-site under KES 1M/mo, no existing POS | Real pain, low ACV, heavy hand-holding. Do not lead with these |

**Decision maker:** the **owner** or **Group Operations Manager**. Not the branch manager (no budget), not the chef (no budget, and threatened by pricing intelligence).

### Call timing for Nairobi restaurants — this matters more than your script

| Window | Verdict |
|---|---|
| **9:00–11:30** | ✅ **Best.** Post-delivery, pre-lunch prep. Owners are doing admin |
| 11:30–14:30 | ❌ Lunch service. You will be hung up on and you'll deserve it |
| **14:30–16:30** | ✅ **Second best.** The lull. Managers are counting |
| 16:30–18:00 | ⚠️ Dinner prep. Only for warm follow-ups |
| 18:00–22:00 | ❌ Service. Never |
| **Mon–Wed** | ✅ Best days |
| Fri/Sat | ❌ Worst. Weekend rush headspace |

**So: today, work 9:00–11:30 and 14:30–16:30. Two blocks. 20 dials each.**

---

## 4. The call — full structure

Sequence is Miner's NEPQ, opened with Voss + Braun, insight from Challenger, closed with Sandler.

### Stage 1 — Opener (accusation audit + permission)

> **You:** "Hi, is that [Name]?"
> **Them:** "Yes…"
> **You:** *(warm, unhurried, slightly slower than normal)*
> "[Name], you're going to hate this — this is a cold call, and I'd guess you've had three people pitch you a POS system this month already."
> *(pause — let the small laugh or the sigh happen)*
> "Can I have 27 seconds to say why I called, and then you can tell me to get lost?"

**Why it works:** The accusation audit (Voss) names the objection before they can. The oddly specific "27 seconds" (not "a minute") signals you'll actually respect their time. The explicit permission to reject lowers pressure (Braun).

**Alternative opener — the no-oriented question:**
> "[Name], is now a ridiculous time to talk for two minutes?"
> "No" → proceed. "Yes" → "Fair enough — is tomorrow morning better, or is Thursday easier?"

### Stage 2 — The poke (problem awareness)

Do **not** pitch. Ask.

> "I work with restaurant groups here in Nairobi. The thing that keeps coming up — and I'm curious whether it's true for you — is that at month end the numbers don't quite match the menu. A dish is priced at 850, but across the month it actually rang through at closer to 780. Discounts nobody logged, mis-keys, staff prices.
> How does that compare with what you're seeing?"

Then **stop talking.** Do not fill the silence. This is the most important pause on the call.

**Their likely answers and your move:**

| They say | You say |
|---|---|
| "Yeah, we suspect that happens." | *(label)* "Sounds like it's been bothering you for a while." → go to Stage 3 |
| "No, our system controls that." | *(neutral, genuinely curious — not combative)* "That's good to hear. Out of interest, how would you know if it happened last Tuesday on one dish?" |
| "How would you even know that?" | "I don't — that's exactly my point. Nobody does until they measure it per dish. Can I ask what you're using now?" |
| "We're fine, thanks." | Go to §5, reflex objection |

### Stage 3 — Situation + consequence

Short. Two or three questions maximum on a cold call.

> "How many sites are you running now?"
> "And how are you currently working out which dishes actually make you money — after cost, after delivery commission?"
> *(whatever they answer)* "How's that been working out for you?"

Then the **consequence question** — this is what creates urgency:

> "If that gap is even 1% of revenue, on your volume that's roughly KES [do the maths out loud] a year walking out the door. What's your sense of whether it's bigger or smaller than that?"

**Do the arithmetic on the call, out loud, using their number.** An owner doing KES 3M/month: 1% = KES 30,000/month = **KES 360,000 a year.** Saying that number slowly is worth more than any feature you could list.

### Stage 4 — The teach (Challenger reframe)

Only now do you say what you do — and keep it to two sentences.

> "So — what we've built is the thing that sits on top of all that. A POS tells you what you sold. It can't tell you what you earned, and it definitely can't tell you what it let walk out the door. Ours does both, on your real numbers, and every morning it gives your managers the three highest-impact things to do for that day's profit."

### Stage 5 — The close (a demo, nothing more)

> "I'm not going to try to sell you a system on a phone call. What I'd like is 15 minutes — I'll run it on real restaurant data and show you exactly what the leak report looks like. If it's not relevant you'll know inside five minutes and I'll leave you alone.
> Is Thursday at 3, or is Friday morning easier?"

**Alternative close — takeaway (Sandler negative-reverse):**
> "Honestly, I don't know yet whether this is a fit for you — it depends on whether you're already tracking margin per dish. Worth 15 minutes to find out either way?"

**Always propose two specific slots. Never "let me know."**

### Stage 6 — Lock it down

- Confirm **WhatsApp number** — this is Kenya; WhatsApp is the channel that works.
- Send the calendar invite **while still on the phone**.
- "I'll send you a one-pager on WhatsApp now so you know what you're walking into."
- Ask: **"Who else should be on the call?"** (Finance/ops presence roughly doubles close rate.)

---

## 5. Objection handling

**Universal method:** *Label → Question → Reframe → Re-close.* Never argue. Never "but". Use "and".

### "We already have a POS."
> "Good — you should have one. *(pause)* Most of the groups we work with kept theirs at first. The reason they still talked to us is that their POS told them what they sold, and nothing about what they earned per dish after cost and delivery commission.
> Does yours flag a dish that's dropped under 40% margin?"
*(Almost always: no. That's the wedge.)*

### "Not interested." *(within 5 seconds — a reflex, not a decision)*
> "Totally fair — you don't know me yet. *(pause)* Can I ask one question and then I'll go? If I could show you, per dish, how much your till undercharged last month — would that be interesting, or genuinely not a priority right now?"

If they hold the no: **"Understood. Thanks for your time"** — and mean it. Log it. Move on. Chasing past this costs you the market's goodwill.

### "Send me an email."
> "Happy to — and can I be honest? Emails like mine get ignored, and you'd be right to ignore it. *(pause)* Give me 90 seconds now, and if it's not relevant I won't send anything at all. Fair?"

If they insist: get the email **and** the WhatsApp, agree a specific follow-up day. "I'll send it now and call you Thursday morning — that alright?"

### "How much does it cost?" *(early — a buying signal, don't fumble it)*
> "It depends on your number of sites and volume, and I'd be guessing if I priced you now. What I can tell you is that we size it against what we find — if it doesn't clear its own cost on the leaks and waste alone, it's not a deal worth doing.
> Let's do the 15 minutes, and I'll price it properly on your actual numbers."

### "It's too expensive." *(later, on price)*
Voss's calibrated question, then silence:
> "I hear you. How am I supposed to make that work?"
Then wait. Let them solve it. **Do not discount reflexively** — restructure instead (fewer sites in phase one, longer term, phased rollout).

### "We tried software before and it failed."
> "That's the most legitimate objection I hear. *(label)* It sounds like you got burned and had to clean it up yourself.
> What broke — was it the software, or was it that nobody showed up after the sale?"
*(Nearly always the second.)*
> "That's why we do it in four days, in person, and train your floor staff ourselves. And there's a paper fallback so service never stops."

### "My staff won't use it / they're not technical."
> "That's the right thing to worry about — a system your floor won't touch is worthless. That's exactly why the kitchen side is a screen with tickets on it and the owner side runs on WhatsApp. Your team already uses WhatsApp all day.
> Who's your most technology-resistant staff member? I'd like them on the demo."

### "I need to think about it."
Sandler:
> "Of course. *(pause)* Just so I don't chase you pointlessly — when people say that to me it usually means one of three things: the money, the timing, or they're not convinced it'll work. Which is closest?"

### "AI is going to change our prices / mess with my menu."
> "It can't, and that's deliberate. Every recommendation is advisory — nothing changes a price or sends a message until a human taps approve, and every approval is logged with who made it. You'll see the approval screen on the demo."
*(This is true and it's in the code — the audit trail is real.)*

### Gatekeeper: "What's this regarding?"
Never pitch the gatekeeper. Be brief, warm, assume the connection.
> "Hi — it's [Name] calling for [Owner]. It's about the margin report on their menu. Is he/she around?"
If blocked: "No problem — when's the best time to catch them? … And is this the best number, or do they prefer WhatsApp?"
**Treat the gatekeeper as a colleague, always.** Get their name and use it next time.

### Voicemail (keep under 20 seconds, leave the number twice)
> "[Name], it's [You] from Leviii, Nairobi — 0*** *** ***.
> I called about something specific: dishes that ring through the till below menu price. Most restaurants leak about 1% of revenue that way and never see it.
> If that's worth 15 minutes — 0*** *** ***. I'll also send a WhatsApp."

**Always follow a voicemail with a WhatsApp within 2 minutes.** That's the message that actually gets read.

---

## 6. WhatsApp follow-up templates

WhatsApp is the primary channel in this market. Keep it short, no attachments on message one.

**After a voicemail:**
> Hi [Name] — [You] from Leviii (just left you a voicemail). We show restaurant owners, per dish, how much their till is undercharging them each month. Worth 15 min? Thursday 3pm or Friday 11am?

**After a good call, before the demo:**
> Great speaking, [Name]. Confirmed for [day/time]. Here's the one-pager: [link to sales pack]. Two things I'll show you: your true profit per dish, and the daily action list. — [You], Leviii

**No-show follow-up:**
> No problem [Name], I know how the day goes. Want me to grab a slot next week, or is this better parked for now?

*(That last clause is deliberate — a no-oriented escape hatch. It gets more replies than pure chasing.)*

---

## 7. The offer (build this before you dial)

Hormozi's value equation says the offer beats the pitch. Ours:

**The Leak Audit Pilot**
- We onboard **one site in four days**.
- Within the first two weeks you get a **Profit Leak Report**: every dish where the till undercharged, extrapolated monthly, plus every dish under 40% margin, plus true delivery-app cost.
- You approve or reject every recommendation — nothing moves on its own.
- Priced per site, monthly, no long lock-in for the pilot site.

**Why it converts:** it collapses time-delay (four days, not a quarter), it makes the likelihood-of-success visible (deterministic math they can audit), and it shrinks effort to almost nothing (we import the menu, we train the staff).

⚠️ **Before you offer any money-back guarantee, clear it with the founder.** Don't invent commercial terms on a call.

---

## 8. Follow-up cadence

Most deals die of neglect, not rejection (Blount, Cardone). Run this for every prospect that didn't say a hard no:

| Touch | Day | Channel | Content |
|---|---|---|---|
| 1 | 0 | Call | The cold call |
| 2 | 0 | WhatsApp | One-liner + one-pager |
| 3 | 2 | Call | Different time of day than touch 1 |
| 4 | 5 | WhatsApp | A single insight — e.g. real delivery commission cost |
| 5 | 9 | Call | "Still worth a look, or should I close your file?" |
| 6 | 16 | WhatsApp | Peer proof — an anonymised leak figure |
| 7 | 30 | Call | Fresh angle, new month |

**"Should I close your file?"** at touch 5 is the highest-response line in the sequence. People answer a takeaway when they'll ignore a chase.

---

## 9. Track this or the month is guesswork

Log every dial. Minimum fields: Restaurant · Contact · Role · Sites · Time called · Outcome · Objection · Next action · Next date.

**Daily target:** 40 dials · 12+ conversations · 3 demos booked.

**Benchmarks to check yourself against:**

| Metric | Healthy | If you're below |
|---|---|---|
| Connect rate | 25–35% | Wrong times — move to 9–11:30 / 14:30–16:30 |
| Conversation → demo | 20–30% | Your poke is weak or you're pitching too early |
| Demo → pilot | 25–40% | Rehearse the demo click-path (`talk-track-internal.md` §4) |
| Hang-ups in first 10s | Under 15% | Your opener sounds like a script. Slow down, add the accusation audit |

**Review daily:** what was the most common objection today, and what's the one line you'll change tomorrow? That's the self-annealing loop applied to selling.

---

## 10. Hard guardrails — never break these on a call

These come straight from `talk-track-internal.md` §6 and the legal reconciliation. Breaking them is worse than losing the deal.

- ❌ **Never quote the 15-minute / 24-7 / automatic-alerting SLA numbers.** Speak to intent until monitoring is wired.
- ❌ **Never promise the plugin marketplace.** It's an SDK, not a store.
- ❌ **Never promise menu-photo / vision.** Declared in routing, not implemented.
- ❌ **Never demo or promise Stripe.** Intentionally disabled — M-Pesa is the real path.
- ❌ **Never promise Strategy-Agent LLM mode or WhatsApp natural-language mode.** Both flag-off; the deterministic versions work.
- ❌ **Never quote MTTR/RTO numbers.** Marked "TBD — to be measured."
- ❌ **Never present the ROI ranges as a guarantee.** They're planning estimates validated against their books.
- ✅ **Use the three-word vocabulary precisely:** **Built** (wired today) · **Rolling out** (built, gated) · **Coming soon** (roadmap). Never blur them.

> Enterprise buyers forgive missing features. They never forgive discovering something was presented as production-ready when it wasn't.

---

## Appendix — the one-page call card

Print this. Keep it in front of you.

```
OPEN    "You're going to hate this — this is a cold call, and you've
         probably been pitched three POS systems this month.
         Can I have 27 seconds?"

POKE    "Dish priced at 850, rings through at 780 all month.
         Discounts nobody logged, mis-keys, staff prices.
         How does that compare with what you see?"
         >>> THEN SHUT UP <<<

SIZE    "How many sites?"
        "How do you work out which dishes actually make money?"
        "How's that working out?"

COST    "1% of revenue = KES ___ a year. Bigger or smaller?"
         (do the maths OUT LOUD, using THEIR number)

TEACH   "A POS tells you what you sold. It can't tell you what you
         earned — or what it let walk out the door."

CLOSE   "15 minutes. Thursday 3, or Friday morning?"

LOCK    WhatsApp number · invite sent now · who else joins?
```

---

*Sources for the methodology research are listed in `docs/sales/gtm-plan.md` §11.*
