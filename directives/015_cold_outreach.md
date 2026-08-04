# Cold Outreach — Door-to-Door & Cold Call SOP

## Purpose
Turn a list of restaurant addresses into booked demos, and booked demos into paying
sites. This is the field manual: where to go, when to walk in, what to say, what to
record, and when to walk away.

Two documents already exist and are **not** duplicated here — read them first:
- `docs/sales/talk-track-internal.md` — the pitch, the demo click-path, the objection
  answers, and the private caveats (what you must not promise).
- `docs/sales/leviii-sales-pack.html` — the leave-behind / brochure.

This directive covers the step *before* those: getting in the door at all.

**The single rule that governs everything below: the goal of a cold visit is not to
sell. It is to book a 20-minute demo with the person who can say yes.** Trying to close
on the doorstep is how you lose the room. You are selling the meeting.

---

## Inputs
- A target list (restaurant name, area, address, phone if known). Build it from
  Google Maps by area, from walking a street, or from referrals.
- The pipeline file (see Tools) — the one source of truth for every lead's state.
- A charged phone with the demo loaded and a **hotspot** (never trust venue wifi),
  plus printed one-pagers.

## Outputs
- Every contacted restaurant recorded in the pipeline with a stage and a next action.
- Booked demos on the calendar.
- Weekly conversion numbers (visits → demos → closes) you can actually steer on.

## Tools
- `execution/outreach_pipeline.py` — the deterministic pipeline tracker. Every lead,
  touch, and stage transition goes through this script. Do not keep the pipeline in
  your head or in WhatsApp chats; both leak and neither is countable.

```
py execution/outreach_pipeline.py add "Mama Ngina Kitchen" --area Westlands --phone +2547...
py execution/outreach_pipeline.py log 3 --outcome gatekeeper --note "owner in Fri am"
py execution/outreach_pipeline.py stage 3 demo_booked --next 2026-08-07
py execution/outreach_pipeline.py today          # who to chase today
py execution/outreach_pipeline.py stats          # conversion by stage
```

---

## Timing — the highest-leverage decision you make

Walking into a restaurant at the wrong hour guarantees a no, regardless of the pitch.
A manager during service is not being rude; they genuinely cannot talk to you.

| Window (EAT) | Verdict | Why |
|---|---|---|
| 07:00–09:30 | Poor | Prep and deliveries. Owner often not in yet. |
| **10:00–11:30** | **Best** | Post-prep lull. Owner doing books/stock. Calm. |
| 12:00–15:00 | **Never walk in** | Lunch rush. You will be resented and remembered for it. |
| **15:00–17:00** | **Best** | Dead hours between services. The classic sales window. |
| 17:00–18:30 | OK | Dinner prep starting; keep it to 3 minutes. |
| 18:30–22:00 | **Never walk in** | Dinner service. |

Day of week: **Tuesday–Thursday** are the money days. Monday is admin chaos and
stock-taking; Friday afternoon the owner's head is already in the weekend rush;
weekends are service. Book demos for Tue–Thu, 10:00 or 15:30.

**Plan the route by geography, not by list order.** Twelve restaurants on one Westlands
street beats four scattered across Nairobi — traffic is the real cost of a field day.

---

## Qualification — who is worth your time

You have limited days. Score a lead before spending a second visit on it.

**Good fit (pursue):**
- 40+ covers a day, or a visibly busy counter.
- Owner-operated or a single decision-maker on site.
- Already takes M-Pesa (they understand digital money and have a till number).
- Multiple sites, or an owner who talks about opening another — the enterprise
  dashboard is the strongest close in the deck.
- Visible operational pain: handwritten tickets, shouting orders to the kitchen,
  a stock cupboard nobody is counting.

**Poor fit (log it, walk away):**
- Tiny kibanda / single-person operation — no budget, no process to systematize.
- A franchise or hotel group where the system is mandated from head office. Ask
  *"do you choose your own systems here, or does head office?"* early; if head
  office, get head office's name and treat it as a separate, longer lead.
- Locked into a POS contract with more than a year left. Log the renewal date and
  come back — that date is the whole opportunity.
- The owner is never reachable and the manager cannot spend money. Two failed
  attempts to reach a decision-maker = park it.

**Disqualify out loud and early.** "Sounds like this isn't for you right now" earns
more respect (and referrals) than three follow-ups to a dead lead.

---

## The door-to-door play

### 1. Read the room before you speak (10 seconds)
Busy? Leave. Come back at a listed window. Nothing else you do matters more.

### 2. Get past the gatekeeper
The first person you meet is a cashier, waiter, or supervisor. They cannot buy, but
they can absolutely stop you. Treat them as an ally, not an obstacle.

> "Hi — I'm [name] from Leviii. I'm not here to sell you anything today. Is the
> owner or the manager around? I've got something short that helps restaurants like
> this one make more from the same covers."

If not in: **get the name and the best time**, not just a phone number.
> "No worries — what's their name? And what's the best day and time to catch them
> here? I'd rather come back than bother them on the phone."

Then log it (`--outcome gatekeeper`) and actually return at that time. Showing up
when you said you would is most of the credibility you will ever have with them.

### 3. The 30-second opener (to the decision-maker)
Say the outcome, never the technology. No "AI", no "platform", no "solution".

> "I'll take two minutes. We run restaurants on one system — the till, the kitchen
> screen, stock, bookings, M-Pesa. The part owners actually care about: every
> morning it messages you the three things to do that day to make more money —
> which dish is quietly losing you cash, what you're about to run out of, which
> customers stopped coming. Can I show you on my phone for ten minutes, or should
> I come back Thursday?"

Then **stop talking.** The silence does the work.

### 4. The hook question (if they don't bite)
Pick the one that fits what you saw walking in:
- "How do you know today which dish actually makes you money after ingredients?"
- "When you run out of something mid-service — how far ahead do you find out?"
- "How many customers came in last month who used to come every week?"

Every one of those is a question they cannot answer, and the product answers all
three. That gap *is* the pitch.

### 5. Close for the meeting, not the sale
> "Give me twenty minutes Thursday at 3. I'll show you your own numbers, not a
> generic demo. If it's not obviously worth it, I'll leave and won't chase you."

Offer **two specific times**, never "when are you free". Put it in the pipeline
before you leave the building — `stage <id> demo_booked --next <date>`.

### 6. Leave-behind + immediate follow-up
Hand over the one-pager with your name and number written on it by hand. Within an
hour, send the WhatsApp confirmation (script below). A booked demo with no written
confirmation is a 50% no-show.

---

## The cold call play

Cold calling works in this market mainly as **follow-up** to a visit or a referral.
Pure cold calls to a restaurant landline mostly reach a busy waiter. Prefer walking in;
call to confirm, chase, and re-book.

Call in the same windows (10:00–11:30, 15:00–17:00). Never during service.

> "Hi, is that [name]? It's [you] from Leviii — I stopped by [restaurant] on Tuesday
> and you said to call this morning. Two things and I'll let you go: I can show you
> what your three highest-earning and three worst-losing dishes are, on your own
> numbers, in twenty minutes. Does Thursday 3pm work, or is Friday morning better?"

**Rules:**
- Name the previous interaction in the first sentence. It converts a cold call into
  a warm one.
- Ask for a decision on a *time*, not on the product.
- Three unanswered calls = switch to WhatsApp. Six touches with no reply = park the
  lead as `cold` and stop. Chasing further burns the brand for a referral you might
  otherwise get later.

---

## Objections at the door

The full objection set is in `talk-track-internal.md` §5–6. These four are the ones
that come up *at the door*, before any demo:

| They say | You say |
|---|---|
| "We already have a POS." | "Good — most of the restaurants we work with did. A POS records what happened. This tells you what to do tomorrow. Twenty minutes and you can judge it yourself." |
| "How much?" | Do not quote on the doorstep — you have no idea of their size yet. "It depends on how many sites and covers, so I'd be guessing. Let me show you what it does first; if it's not worth several times the price you'll know inside ten minutes." |
| "I'm too busy." | "That's exactly why I'm not asking for time now. Thursday at 3 or Friday at 10?" |
| "Send me an email / leave your card." | "Happy to — but you'll never read it. Give me twenty minutes Thursday and if I'm wasting your time, throw me out." Then hand over the one-pager and log it as `brush_off`, not as a lead. |

**Do not**, at the door or on a call: quote the SLA response-time numbers, promise the
plugin marketplace, promise menu-photo/vision, or demo WhatsApp natural-language mode.
See `talk-track-internal.md` §6 for why — all four are things the product does not do
today, and one caught over-claim ends the deal.

---

## Follow-up cadence

WhatsApp beats email in this market. Every message must carry a *new* reason to reply,
never "just checking in".

| When | Channel | Message |
|---|---|---|
| Within 1h of the visit | WhatsApp | "Great meeting you [name] — [you] from Leviii. Confirmed for Thu 3pm at [restaurant]. I'll bring the numbers on your own menu. — [name]" |
| Morning of the demo | WhatsApp | "Still good for 3pm today? I'll be 5 minutes early." |
| Demo + 1 day | WhatsApp | One screenshot from *their* demo + "This was the dish losing you the most — happy to walk your manager through the fix." |
| Demo + 4 days | Call | Ask directly: "What's stopping this from being a yes?" |
| Demo + 10 days | WhatsApp | Final: "I'll stop chasing — if it's a no for now, no hard feelings. Worth a look again when [renewal date / new site]?" |
| No reply after that | — | Mark `cold`. Stop. |

A "no" that ends cleanly is a referral or a re-open in six months. A "no" you nagged
into existence is neither.

---

## Daily and weekly targets

Field work collapses without a number to hit. Track them with `stats`.

| Metric | Target | Meaning |
|---|---|---|
| Doors per field day | 12–15 | With a geographic route, in the two good windows. |
| Decision-maker conversations | 4–6 | If well below, your timing is wrong, not your pitch. |
| Demos booked per field day | 2–3 | If conversations are fine but bookings are not, the close is weak — you are pitching product instead of asking for a time. |
| Demo show-up rate | >70% | Below that, your confirmation follow-up is failing. |
| Demo → close | 1 in 4–5 | Below that, you are demoing unqualified leads. |

**Diagnose with the funnel, not with feelings.** Each of those rows fails for a
different, fixable reason. Look up which row broke before changing anything.

---

## Edge cases and learnings

- **Never walk in during service.** Repeated because it is the single most common
  self-inflicted failure.
- **"The owner is in Mombasa / abroad."** Extremely common with Nairobi restaurants.
  Get the WhatsApp number, send a 60-second screen-recorded demo instead of trying
  to schedule a call across time zones.
- **The manager loves it, the owner has never heard of you.** You are talking to a
  champion, not a buyer. Ask directly: "Would it help if I showed the owner myself,
  or would you rather take it to them?" Then arm them: leave two one-pagers.
- **Price asked three times before a demo** = they are either a serious buyer with
  budget or a tyre-kicker. Answer on the third ask with a range tied to sites and
  covers, and immediately re-anchor on the demo.
- **Venue wifi will fail during your demo.** Hotspot, always. Rehearse the click-path
  so you can narrate through a slow load without dead air.
- **Bring the phone charged to 100%.** A dying phone mid-demo has killed more deals
  than any objection.
- **Log the visit before you get in the car.** Notes written an hour later are wrong,
  and a lead you cannot remember is a lead you will not close.

---

## Self-annealing
This directive is a living document. After every field day, if you learn something —
a window that works better in a given area, an objection you had no answer for, a
qualification signal that predicted a close — add it above. When a target number is
consistently missed, change the play, not the target, and record what you changed.
