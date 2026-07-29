"use client";

/**
 * frontend/src/components/ai/HowItWorks.tsx
 * ──────────────────────────────────────────
 * Plain-language explainer layer, shared across the AI Command Center, ROI and
 * Marketing pages. Every AI/analytics module speaks analyst jargon a normal
 * restaurant owner won't recognise ("contribution margin", "velocity ratio",
 * "Plowhorse"). This is the translation layer: what each brain does, where its
 * numbers come from, and what every term means — in plain language.
 *
 * Definitions are kept faithful to the backend that computes them (40% margin
 * floor / 35% food-cost ceiling in ai/pricing/analysis.py; the minutes-saved
 * benchmarks in ai/roi/savings.py; the 21-day lapse window and consent gate in
 * ai/whatsapp/brain.py). This is static copy — it invents no numbers, so the
 * server-side grounding guarantee (ai/reasoning/narrator.py) is untouched.
 */

import { useState } from "react";
import { Info, ChevronDown, AlertTriangle } from "lucide-react";

export interface Explainer {
    what: string;
    where: string;
    caveat?: string;
    terms: { t: string; d: string }[];
}

export const AI_EXPLAIN: Record<string, Explainer> = {
    profit: {
        what: "Shows where your money is really going — true profit on each dish after ingredient cost, and exactly where you're losing it.",
        where: "Your last 30 days of real orders plus the cost price you entered for each menu item.",
        caveat: "If cost prices are wrong or missing, these numbers are wrong. Keep them up to date.",
        terms: [
            { t: "Gross margin", d: "Out of every KES 100 a dish earns, how much is left after paying for ingredients. 55%+ is healthy." },
            { t: "Food cost %", d: "How much of the price goes to ingredients. Under 35% is healthy." },
            { t: "Profit leak", d: "A dish priced too low for what it costs you — shown as shillings lost per month." },
            { t: "Portion drift", d: "The menu says one price but the till keeps charging less — often quiet staff discounts. Worth checking." },
            { t: "Daypart", d: "Which part of the day (breakfast/lunch/dinner) makes the most money after cost." },
            { t: "Channel", d: "Walk-in vs delivery. After Uber/Glovo/Bolt take 20–25%, delivery often earns much less." },
        ],
    },
    decisions: {
        what: "Collects every recommendation from all your AI brains — pricing, stock, suppliers, menu, staffing, marketing — and ranks them into one 'do this first' list.",
        where: "Each brain's own findings, scored together by four things: how much money it moves, how sure we are, how risky it is, and how hard it is to do.",
        caveat: "Only pricing gives an exact shillings-per-month figure today. Operational fixes (reorder, staffing, suppliers) are ranked on confidence, risk and effort — never on a made-up money number.",
        terms: [
            { t: "Priority score", d: "0–100 overall — how worth-doing this is, blending impact, confidence, safety and ease. Higher = do it sooner." },
            { t: "Impact", d: "How much money the change moves per month. Empty stars mean the brain didn't put a shilling figure on it." },
            { t: "Ease", d: "How little effort it takes. More stars = quicker to do (a price change is one click; renegotiating a supplier isn't)." },
            { t: "Safety", d: "How low the downside is. More stars = safer to try with little risk of backfiring." },
            { t: "Confidence", d: "How sure the brain is, based on how much of your data backs the recommendation." },
        ],
    },
    strategy: {
        what: "Give it a business goal and it acts like a CEO: it asks every specialist brain what they'd do, tests the best ideas, then hands you one ranked plan of steps.",
        where: "The ranked decisions from all your brains, the what-if simulator, the knowledge graph (what affects what), and your revenue outlook — combined into a sequence.",
        caveat: "It only suggests. Nothing changes until you approve each step (a price change, a promo, a reorder) the normal way. If no AI provider is set up, it still gives you the ranked plan without the written narrative.",
        terms: [
            { t: "Goal", d: "What you want to achieve, in plain words — e.g. 'increase monthly profit by KES 100,000' or 'cut waste'." },
            { t: "Plan step", d: "One concrete action, in priority order — the biggest, safest, easiest wins first." },
            { t: "Reasoning trace", d: "The receipts: which brains the agent consulted and what each said, so the plan isn't a black box." },
            { t: "Ranked mode", d: "Shown when no AI writer is connected — you still get the prioritised plan, just without the written explanation." },
        ],
    },
    twin: {
        what: "A forward look at your revenue that mixes your own sales pattern with what's coming on the calendar — public holidays and school breaks — so you can plan stock and staff ahead.",
        where: "Your last 30 days of sales for the day-by-day baseline, plus a built-in list of Kenyan public holidays and school-term breaks. Weather and match days can be added later.",
        caveat: "It's a projection, not a promise. Holiday and school-break effects are sensible general assumptions, not measured for your specific restaurant — shown separately from your baseline so you can see the difference. The further out, the less certain.",
        terms: [
            { t: "Baseline", d: "What you'd earn from your normal weekly pattern alone, with no special days." },
            { t: "Projected", d: "The baseline adjusted up or down for holidays and school breaks in the window." },
            { t: "Uplift", d: "The difference the calendar makes — extra revenue expected from those special days." },
            { t: "Range", d: "A low-to-high band. A wider band means less certainty (further out, or a big special day)." },
            { t: "Demand mover", d: "A specific upcoming day a holiday or school break is expected to change your takings." },
        ],
    },
    simulate: {
        what: "Lets you try a price change on paper first. Pick a dish, propose a new price, and see what would likely happen to sales, profit and margin before you commit.",
        where: "Your last 30 days of sales for that dish, plus a demand model that assumes people buy a bit less when a price goes up and a bit more when it drops — tuned by how hot or slow the dish is running.",
        caveat: "It's a projection, not a promise. The satisfaction figure is a rough proxy, not a real survey. Big price jumps are less reliable — the model is most accurate near the current price.",
        terms: [
            { t: "Verdict", d: "YES = projected to help with little risk. CAUTION = mixed (test it). NO = projected to hurt profit or break the healthy margin floor." },
            { t: "Sales change", d: "How much order volume is expected to move. Prices up usually means slightly fewer orders." },
            { t: "Profit / mo", d: "The projected change in monthly profit after ingredient cost — the number that actually matters." },
            { t: "Elasticity", d: "How sensitive this dish is to price. A hot-selling dish takes a price rise better than a slow one." },
            { t: "Confidence", d: "How much to trust the projection, based on how much sales history backs it and how big the change is." },
        ],
    },
    pricing: {
        what: "Watches how fast each dish sells and whether its price still makes sense, then suggests small changes.",
        where: "Your last 30 days of sales speed plus cost prices. New dishes (under 14 days of data) only get margin fixes, not demand-based changes.",
        caveat: "Depends on correct cost prices to judge margin.",
        terms: [
            { t: "SURGE", d: "Selling much faster than usual and still profitable → raise the price a little (max 15%) while it's hot." },
            { t: "REPRICE", d: "Margin is below the healthy 40% floor → raise it so you actually make money on the dish." },
            { t: "STIMULATE", d: "Selling slowly but good margin → drop about 10% to pull more orders." },
            { t: "Velocity", d: "How fast it's selling now vs its own normal. 1.0 = normal, 1.3 = 30% hotter, 0.6 = 40% slower." },
            { t: "Cooldown", d: "After a suggestion, the same dish won't be raised again for 7 days." },
            { t: "Delivery gap", d: "A dish that looks fine in-store but loses money once the delivery app takes its cut." },
        ],
    },
    menu: {
        what: "Sorts every dish by how popular and how profitable it is, so you know what to promote, fix, or cut.",
        where: "Your last 30 days of orders plus cost prices.",
        terms: [
            { t: "Star", d: "Popular AND profitable — your winners. Keep them front and centre." },
            { t: "Plowhorse", d: "Popular but thin margin — nudge the price up or trim portion cost." },
            { t: "Puzzle", d: "Good margin but few order it — promote it or move it where people see it." },
            { t: "Dog", d: "Few orders and little money — fix the recipe or remove it." },
            { t: "Popularity index", d: "A dish counts as 'popular' if it sells at least 70% of the average — one or two bestsellers pull the plain average up unfairly." },
            { t: "Menu score", d: "Overall menu health out of 100 — mostly what your menu is made of (Stars vs Dogs), plus costing and trend." },
        ],
    },
    labor: {
        what: "Checks whether your staffing cost is in line with sales, and flags expensive overtime.",
        where: "Your staff shifts and hours plus sales over the last 30 days.",
        terms: [
            { t: "Labor cost %", d: "Wages as a share of sales. Around 30% or below is typical; higher eats into profit." },
            { t: "Sales per hour", d: "Revenue earned for each staff hour worked — higher means a more efficient shift." },
            { t: "Overtime cost", d: "Extra pay from hours beyond normal — usually a quick target to trim." },
        ],
    },
    health: {
        what: "One 0–100 score for the whole business, built from five areas, with your biggest fixable weaknesses listed first.",
        where: "A weighted blend of five checks below, each scored from your live data.",
        terms: [
            { t: "Menu Health", d: "How many Stars vs Dogs are on your menu." },
            { t: "Revenue Trend", d: "Whether sales are rising or falling week-over-week." },
            { t: "Kitchen Efficiency", d: "Prep speed at your stations during the busy hours." },
            { t: "Inventory Status", d: "Low-stock and spoilage-risk items." },
            { t: "Reservation Reliability", d: "No-shows vs completed bookings." },
        ],
    },
    dataquality: {
        what: "Checks that every dish has a sensible cost price — because your profit and pricing numbers are only as accurate as the cost prices you enter.",
        where: "Your menu items' price and cost price, cross-checked with your last 30 days of sales so the most-sold gaps show first.",
        caveat: "A missing or wrong cost price silently distorts profit, margin, and every price suggestion — this is the fix-at-the-source list.",
        terms: [
            { t: "No cost set", d: "No cost price entered — the dish is left out of your profit figures entirely." },
            { t: "Sold at a loss", d: "Ingredients cost as much as or more than the price — you lose money on each one." },
            { t: "Cost looks like a typo", d: "Cost is only a tiny fraction of the price — usually a wrong-units or missing-digit slip." },
            { t: "Very thin margin", d: "Under 10% left after ingredients — real, or a data-entry error worth checking." },
        ],
    },

    supply: {
        what: "Scores each supplier on how reliably they deliver on time and whether their prices are creeping up, and flags overdue orders.",
        where: "Your purchase orders and their delivery dates over recent history, plus the cost you were charged each time.",
        terms: [
            { t: "Reliability", d: "The share of a supplier's orders that arrived on time. Below 85% is a reason to consider switching." },
            { t: "Lead time variance", d: "How many days later (or earlier) they actually deliver vs what they promised." },
            { t: "Cost trend", d: "Whether this supplier's prices are rising, falling, or steady over their recent orders." },
            { t: "Overdue order", d: "A purchase order that's past its expected date and hasn't been marked delivered." },
        ],
    },

    /* ── ROI page explainers ─────────────────────────────────────────────── */
    roi_overview: {
        what: "Three separate ways the software pays for itself — kept apart on purpose so the picture is honest, never inflated into one big number.",
        where: "Your real activity over the last 30 days: automated messages sent, analysis runs, approved price changes, and the money the AI has flagged but you haven't acted on yet.",
        caveat: "We never add the three totals together. Time-saved is an automation estimate, captured money already happened, and opportunities haven't been realised yet — summing them would double-count.",
        terms: [
            { t: "Time saved", d: "Staff hours the software did for you (sending messages, running analysis), turned into money using your own staff wage." },
            { t: "Profit captured", d: "Extra money you already earned by approving the AI's price suggestions. The only 'already happened' figure." },
            { t: "Opportunities", d: "Money the AI has found but you haven't captured yet — approve or action these to bank it." },
        ],
    },
    roi_time: {
        what: "The staff hours the software quietly did for you — every automated message and analysis run — priced at your own wage rate.",
        where: "A count of automated actions in the last 30 days × a conservative minutes-saved estimate for each, × your staff's average hourly wage.",
        caveat: "The minutes-per-action figures are deliberately conservative estimates, not stopwatch measurements — they're shown so you can check them.",
        terms: [
            { t: "Morning briefing", d: "~10 min saved each — a manager compiling the day's numbers by hand." },
            { t: "Analysis run (pricing/profit)", d: "~25–30 min saved each — a manual margin or repricing pass." },
            { t: "Reminder / receipt / promo", d: "1–3 min saved each — a text a staff member would otherwise send by hand." },
            { t: "Your wage rate", d: "Uses your active staff's average hourly pay. If none is set yet, it falls back to KES 250/hr and says 'estimated'." },
        ],
    },
    roi_captured: {
        what: "The extra profit you have already banked because you approved a price change the AI recommended.",
        where: "Every pricing recommendation you APPROVED in the last 30 days, using the monthly-impact figure calculated for it at approval time.",
        terms: [
            { t: "Approved recommendation", d: "A SURGE/REPRICE/STIMULATE suggestion you accepted — the change is live on your menu." },
            { t: "Monthly impact", d: "The extra profit per month that price change is expected to earn, based on how fast the dish sells." },
        ],
    },
    roi_opportunities: {
        what: "Money the AI has already found sitting on the table — you just haven't acted on it yet.",
        where: "Live findings from the profit, pricing, inventory, reservations and labor brains, each shown with where it came from.",
        caveat: "This is potential, not banked money. It moves into 'Profit captured' only once you act — approve a price, cut the waste, reduce the overtime.",
        terms: [
            { t: "Pending price changes", d: "Price suggestions waiting for your approval — the margin they'd earn." },
            { t: "Margin / portion leaks", d: "Dishes sold below a healthy margin, plus tills charging less than the menu price." },
            { t: "Waste / spoilage", d: "Stock likely to be thrown away — its cost, which a timely special could recover." },
            { t: "No-shows / overbooking", d: "Booking revenue at risk, and covers you could safely recover." },
            { t: "Overtime", d: "Extra wage cost flagged for review." },
        ],
    },
    roi_net: {
        what: "The honest bottom line: for every shilling your AI costs to run, how many shillings of real value it gave back.",
        where: "Value = the two 'real money' figures on this page — staff time saved (priced at your wage) plus profit you captured by approving price changes. Cost = your AI's actual token spend over the last 30 days, priced by the same table AI Ops uses.",
        caveat: "Opportunities you haven't acted on yet are deliberately left out — this ratio only counts money that has actually moved. It only appears once there's real AI spend to divide by.",
        terms: [
            { t: "Value delivered", d: "Time-saved money + profit captured. Never includes un-actioned opportunities." },
            { t: "AI cost", d: "What the language-model calls cost you this month, estimated from token usage at public list prices." },
            { t: "× return", d: "Value ÷ cost. A 12× means every KES 1 of AI returned about KES 12 of value." },
        ],
    },
    roi_capacity: {
        what: "How much more you could serve with the same staff — a throughput story, deliberately NOT turned into money.",
        where: "Your kitchen's ticket times and bottlenecks from the KDS over the last 30 days.",
        caveat: "We don't convert this to shillings because that needs assumptions we can't verify — it's shown as real kitchen facts instead.",
        terms: [
            { t: "Avg order time", d: "How long a ticket takes from fired to ready, on average." },
            { t: "Bottleneck", d: "A station that repeatedly slows the whole ticket down." },
            { t: "Reclaimable delay", d: "Minutes the AI estimates you could win back by fixing the flagged bottlenecks." },
        ],
    },

    /* ── Marketing / Campaigns explainers ────────────────────────────────── */
    marketing: {
        what: "Turns what the AI already knows about your menu, stock and customers into specific offers worth running — and tells you why each one makes sense.",
        where: "Your lapsed regulars, high-margin dishes that under-sell, stock at spoilage risk, and slow parts of the week.",
        caveat: "Nothing is sent automatically. The AI suggests; you approve every send. Messages only reach customers who gave consent at checkout and haven't opted out.",
        terms: [
            { t: "Offer", d: "A specific deal to run (e.g. 10% off, buy-one-get-one, happy hour) — with the exact wording that will be sent." },
            { t: "Why", d: "The reason this offer is worth it, in plain language, tied to your real numbers." },
            { t: "Margin-safe", d: "We've checked the discount still leaves a healthy margin — you won't be selling below cost." },
            { t: "Audience", d: "How many customers the offer can legally reach right now." },
        ],
    },
    winback: {
        what: "Finds regulars who used to come in but have gone quiet, and drafts a warm, personal message to bring them back.",
        where: "Customers whose last order was 21+ days ago, ranked by how much they used to spend, with their favourite dish attached.",
        caveat: "Opted-out customers are never contacted. You review the list and approve the send — it's not automatic.",
        terms: [
            { t: "Lapsed regular", d: "Someone who ordered before but hasn't in 21+ days — the sweet spot for a gentle nudge." },
            { t: "Favourite dish", d: "The item they ordered most — named in the message to make it personal." },
            { t: "Recoverable value", d: "Roughly what these customers used to spend — what you stand to win back." },
            { t: "The offer", d: "A small 'welcome back' incentive (e.g. 10% off next visit) attached to the message." },
        ],
    },
    consent: {
        what: "The safety rules that decide who a campaign is allowed to reach — so you stay on the right side of your customers and the law.",
        where: "The consent a customer gave at checkout, and the global STOP opt-out list.",
        terms: [
            { t: "Consent", d: "A positive opt-in a customer gave when ordering — required before any marketing message." },
            { t: "Opt-out (STOP)", d: "Anyone who replied STOP is suppressed everywhere, forever — automatically skipped." },
            { t: "Reachable audience", d: "Customers who both gave consent and haven't opted out — the only people a promo goes to." },
            { t: "Send cap", d: "A safety limit on how many messages one campaign can fire, so nothing runs away." },
        ],
    },
};

export function HowItWorks({ id }: { id: keyof typeof AI_EXPLAIN | string }) {
    const [open, setOpen] = useState(false);
    const e = AI_EXPLAIN[id];
    if (!e) return null;
    return (
        <div className="mt-1">
            <button
                onClick={() => setOpen((v) => !v)}
                aria-expanded={open}
                // py-1.5/-my-1.5 lifts the touch target past the 24px WCAG 2.5.8
                // floor (measured 17px tall) without shifting the layout.
                className="flex items-center gap-1 py-1.5 -my-1.5 text-[11px] text-[#8a8a8a] hover:text-[#d4a853] transition-colors"
            >
                <Info className="w-3 h-3" />
                <span>How this works</span>
                <ChevronDown className={`w-3 h-3 transition-transform ${open ? "rotate-180" : ""}`} />
            </button>
            {open && (
                <div className="mt-2 rounded-lg border border-[#1a1a1a] bg-[#0a0a0a] p-3 space-y-2.5">
                    <p className="text-xs text-[#a3a3a3] leading-relaxed">{e.what}</p>
                    <p className="text-[11px] text-[#7e7e7e]">
                        <span className="text-[#8a8a8a] font-medium">Where this comes from:</span> {e.where}
                    </p>
                    {e.caveat && (
                        <p className="text-[11px] text-amber-400/80 flex gap-1.5">
                            <AlertTriangle className="w-3 h-3 flex-shrink-0 mt-0.5" />
                            <span>{e.caveat}</span>
                        </p>
                    )}
                    <div className="pt-1 border-t border-[#1a1a1a] space-y-1.5">
                        <p className="text-[10px] uppercase tracking-wide text-[#7e7e7e] font-semibold">What the words mean</p>
                        {e.terms.map((term) => (
                            <p key={term.t} className="text-[11px] text-[#8a8a8a] leading-snug">
                                <span className="text-[#e5e5e5] font-medium">{term.t}</span> — {term.d}
                            </p>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
