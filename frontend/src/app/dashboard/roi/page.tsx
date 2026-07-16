"use client";

/**
 * /dashboard/roi — Time & Money Saved
 *
 * Pitch-facing ROI view: how many staff hours the software automated away
 * (converted to money via this restaurant's own wage data), extra profit
 * already captured via approved pricing recommendations, and opportunities
 * the AI has flagged but the owner hasn't acted on yet.
 *
 * Mirrors the shape of GET /ai/roi (backend/ai/roi/savings.py) — three
 * distinct totals, deliberately never summed into one number: time-saved
 * money is an automation estimate, captured money already happened, and
 * opportunities are forward-looking and unrealized.
 *
 * This page leans on the shared explainer toolkit (HowItWorks / NarrativeBlock)
 * so a non-technical owner can see, for every figure, WHAT it is, WHERE it comes
 * from, and WHY it's worth money — including a plain "saved every day" framing.
 */

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { formatKES } from "@/lib/format";
import { HowItWorks } from "@/components/ai/HowItWorks";
import { NarrativeBlock, type Narrative } from "@/components/ai/NarrativeBlock";
import { Clock, TrendingUp, Target, RefreshCw, AlertTriangle, Zap, ChefHat, Info, ArrowUpRight, ArrowDownRight, Scale, CalendarClock } from "lucide-react";

interface RoiBreakdownItem {
    category: string;
    count: number;
    minutes_per_action: number;
    total_minutes: number;
}

interface RoiData {
    window_days: number;
    time_saved: {
        hours_saved_30d: number;
        money_saved_cents: number;
        avg_hourly_rate_cents: number;
        hourly_rate_is_estimated: boolean;
        breakdown: RoiBreakdownItem[];
        hours_saved_prev_30d?: number;
        money_saved_prev_cents?: number;
        hours_change_pct?: number | null;
    };
    money_captured: {
        monthly_impact_cents: number;
        recommendations_approved: number;
        prev_monthly_impact_cents?: number;
        change_pct?: number | null;
        all_time_monthly_impact_cents?: number;
        all_time_approved?: number;
    };
    opportunities: { source: string; label: string; monthly_value_cents: number }[];
    capacity: {
        avg_order_minutes: number;
        orders_per_day: number;
        bottlenecks_found: number;
        reclaimable_delay_minutes: number;
    } | null;
    economics?: {
        ai_cost_cents: number;
        value_delivered_cents: number;
        roi_multiple: number | null;
    };
    projection?: {
        annual_hours_saved: number;
        annual_money_saved_cents: number;
        annual_captured_cents: number;
    };
    narrative?: Narrative;
    error?: string;
}

// Small signed-percentage delta chip. Green when up, muted red when down,
// nothing at all when there's no prior baseline (null) — never a fake "0%".
function TrendChip({ pct }: { pct?: number | null }) {
    if (pct === null || pct === undefined) return null;
    const up = pct >= 0;
    return (
        <span className={`inline-flex items-center gap-0.5 text-[11px] font-medium ${up ? "text-emerald-400" : "text-red-400"}`}>
            {up ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
            {Math.abs(pct)}% vs prior 30d
        </span>
    );
}

const CATEGORY_LABELS: Record<string, string> = {
    morning_briefing: "Morning briefings sent",
    reservation_reminder: "Reservation reminders sent",
    no_show_winback: "No-show win-back messages",
    receipt: "Receipts sent",
    promo: "Promo messages sent",
    campaign_winback: "Win-back campaign messages",
    feedback_alert: "Feedback alerts handled",
    slow_day_alert: "Slow-day alerts sent",
    reorder_request: "Reorder requests sent",
    supplier_late: "Supplier delay alerts",
    stock_depleted: "Stock-out alerts",
    orchestrated_stock_critical: "Critical stock alerts",
    pricing_intelligence: "Pricing analysis runs",
    labor_intelligence: "Labor analysis runs",
    profit_intelligence: "Profit analysis runs",
    inventory_predictor: "Inventory analysis runs",
    supply_chain_intelligence: "Supplier analysis runs",
};

// Plain-language "what a staff member would have done by hand" for each
// automated action — the reason it saves the minutes it does. Faithful to the
// audit comments in backend/ai/roi/savings.py.
const CATEGORY_WHY: Record<string, string> = {
    morning_briefing: "A manager compiling the day's numbers by hand every morning.",
    reservation_reminder: "A staff member calling or texting each guest to confirm.",
    no_show_winback: "Someone calling a no-show to re-book them.",
    receipt: "Manually texting or printing each receipt.",
    promo: "Writing and sending one promo message.",
    campaign_winback: "Drafting and sending one win-back message.",
    feedback_alert: "Noticing a bad review and deciding what to do.",
    slow_day_alert: "Spotting a slow day early enough to react.",
    reorder_request: "Checking stock and messaging a supplier to reorder.",
    supplier_late: "Chasing a late supplier delivery.",
    stock_depleted: "Realising an item ran out and alerting the floor.",
    orchestrated_stock_critical: "Catching a critical stock-out before service.",
    pricing_intelligence: "A manual competitor / margin repricing pass.",
    labor_intelligence: "A manual overtime and scheduling review.",
    profit_intelligence: "A manual contribution-margin analysis.",
    inventory_predictor: "A manual stock-level review.",
    supply_chain_intelligence: "A manual supplier-performance review.",
};

// Where each opportunity line comes from and how to capture it.
const OPP_SOURCE_EXPLAIN: Record<string, string> = {
    pricing_pending: "From Pricing Intelligence — price changes waiting for your approval. Approve them and this becomes captured profit.",
    profit_leaks: "From Profit Intelligence — dishes selling below a healthy margin. Reprice or trim portion cost.",
    portion_drift: "From Profit Intelligence — the till keeps charging less than the menu price (quiet discounts). Tighten till discipline.",
    inventory_waste: "From Inventory — stock likely to spoil. A timely special turns it into sales instead of waste.",
    no_show_prevention: "From Reservations — booking revenue at risk from no-shows. Reminders and small deposits recover it.",
    overbooking_recovery: "From Reservations — covers you could safely recover with light, controlled overbooking.",
    overtime_reduction: "From Labor — overtime cost flagged for review. Rebalance shifts to trim it.",
};

function EmptyState() {
    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-[#e5e5e5]">Time & Money Saved</h1>
                <p className="text-[#525252] mt-1 text-sm">Getting started</p>
            </div>
            <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-8 text-center space-y-4">
                <Clock className="w-12 h-12 text-[var(--accent)] mx-auto" />
                <h2 className="text-[#e5e5e5] font-semibold text-lg">No automation activity yet</h2>
                <p className="text-[#525252] text-sm max-w-md mx-auto">
                    Once the AI starts sending WhatsApp messages, running analysis, or
                    you approve a pricing recommendation, this page will show exactly
                    how many hours and how much money it&apos;s saved you — and how much
                    it&apos;s saving you each day.
                </p>
            </div>
        </div>
    );
}

export default function RoiDashboard() {
    const { user } = useAuth();
    const [data, setData] = useState<RoiData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

    const restaurantName = (user as any)?.restaurant_name || "Your Restaurant";

    const fetchData = async () => {
        setLoading(true);
        setError("");
        try {
            const res = await api.get("/ai/roi");
            setData(res.data);
            setLastUpdated(new Date());
        } catch (e: any) {
            setError(e?.response?.data?.detail || e?.message || "Could not load ROI data");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchData(); }, []);

    if (loading) {
        return (
            <div className="space-y-4">
                <div className="bg-[#141414] rounded-xl h-8 w-48 animate-pulse" />
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {[...Array(3)].map((_, i) => (
                        <div key={i} className="bg-[#141414] rounded-xl h-32 animate-pulse" />
                    ))}
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[50vh] space-y-4">
                <AlertTriangle className="w-10 h-10 text-amber-400" />
                <p className="text-[#e5e5e5] font-medium">Could not load ROI data</p>
                <p className="text-[#525252] text-sm text-center max-w-sm">{error}</p>
                <button
                    onClick={fetchData}
                    className="px-4 py-2 bg-[var(--accent)] text-[#0a0a0a] font-semibold rounded-lg text-sm hover:bg-[var(--accent-hover)]"
                >
                    Retry
                </button>
            </div>
        );
    }

    // No payload at all (shouldn't normally happen without an error) — keep the
    // getting-started guide as a genuine fallback.
    if (!data) {
        return <EmptyState />;
    }

    // "Sparse" = every pillar is still zero (a new restaurant, or the AI hasn't
    // done measurable work yet). We deliberately no longer hide the whole page
    // in this case — the owner should always SEE the ROI dashboard (and that it
    // is real and populating), with a gentle banner instead of a blank
    // placeholder that reads as "the feature is missing".
    const isSparse =
        data.time_saved.hours_saved_30d === 0 &&
        data.money_captured.monthly_impact_cents === 0 &&
        data.opportunities.length === 0 &&
        !data.capacity;

    const ts = data!.time_saved;
    const mc = data!.money_captured;
    const opps = data!.opportunities;
    const cap = data!.capacity;
    const econ = data!.economics;
    const proj = data!.projection;
    const oppsTotal = opps.reduce((sum, o) => sum + o.monthly_value_cents, 0);

    // "Saved every day" framing — the owner's core question. The window is 30
    // days, so per-day = window total / window_days.
    const days = data!.window_days || 30;
    const hoursPerDay = Math.round((ts.hours_saved_30d / days) * 10) / 10;
    const moneyPerDayCents = Math.round(ts.money_saved_cents / days);

    return (
        <div className="space-y-6">
            <div className="flex items-start justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-[#e5e5e5]">Time & Money Saved</h1>
                    <p className="text-[#525252] mt-1 text-sm">
                        {restaurantName} — last {days} days
                    </p>
                </div>
                <button
                    onClick={fetchData}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#141414] border border-[#262626] text-[#737373] hover:text-[#e5e5e5] text-sm transition-colors"
                >
                    <RefreshCw className="w-3.5 h-3.5" />
                    <span>{lastUpdated ? lastUpdated.toLocaleTimeString() : "Refresh"}</span>
                </button>
            </div>

            {/* Still gathering data — shown instead of hiding the whole page, so
                the owner always sees the ROI dashboard exists and is filling in. */}
            {isSparse && (
                <div className="rounded-xl border border-[var(--accent)]/25 bg-[var(--accent)]/[0.06] p-4 flex items-start gap-3">
                    <Clock className="w-5 h-5 text-[var(--accent)] flex-shrink-0 mt-0.5" />
                    <div>
                        <p className="text-sm font-medium text-[#e5e5e5]">Your ROI dashboard is still gathering data</p>
                        <p className="text-[#737373] text-xs mt-1 max-w-xl">
                            As the AI sends messages, runs analysis, and you approve pricing recommendations
                            on the AI page, these numbers start filling in — you&apos;ll see hours saved,
                            profit captured, and money left on the table, updated every day.
                        </p>
                    </div>
                </div>
            )}

            {/* Top explainer — the three-totals model, and why they're never summed */}
            <div className="rounded-xl border border-[var(--accent)]/25 bg-[var(--accent)]/[0.04] p-5">
                <div className="flex items-center gap-2 text-[var(--accent)] mb-1">
                    <Zap className="w-4 h-4" />
                    <p className="text-sm font-semibold text-[#e5e5e5]">How your AI is paying for itself</p>
                </div>
                <p className="text-sm text-[#a3a3a3] leading-relaxed">
                    Every day your AI agents quietly do work a staff member would otherwise
                    do by hand, catch money leaking out of the business, and spot ways to
                    earn more. Below are the <span className="text-[#e5e5e5] font-medium">three separate ways</span> that
                    shows up — kept apart on purpose so the picture stays honest, never
                    inflated into one big number.
                </p>
                <HowItWorks id="roi_overview" />
            </div>

            {/* Daily savings headline — directly answers "how much each day" */}
            <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/[0.05] p-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div>
                    <p className="text-xs uppercase tracking-widest text-emerald-400 mb-1">Saved every day, on average</p>
                    <p className="text-3xl font-black text-[#e5e5e5]">
                        {hoursPerDay} hrs <span className="text-[#525252] text-xl font-bold">·</span> {formatKES(moneyPerDayCents)}
                    </p>
                </div>
                <p className="text-[#737373] text-xs max-w-xs sm:text-right">
                    Averaged from the last {days} days of automated work, priced at{" "}
                    {ts.hourly_rate_is_estimated ? "an estimated wage" : "your own staff wages"}.
                    That&apos;s time your team gets back to run the floor.
                </p>
            </div>

            {/* Hero stats — three distinct totals, never summed */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-6">
                    <div className="flex items-center gap-2 text-emerald-400 mb-2">
                        <Clock className="w-4 h-4" />
                        <p className="text-xs uppercase tracking-widest">Time saved</p>
                    </div>
                    <p className="text-3xl font-black text-[#e5e5e5]">{ts.hours_saved_30d} hrs</p>
                    <p className="text-[#525252] text-sm mt-1">
                        ≈ {formatKES(ts.money_saved_cents)}
                        {ts.hourly_rate_is_estimated ? " (estimated wage)" : " (your staff wages)"}
                    </p>
                    <div className="mt-1"><TrendChip pct={ts.hours_change_pct} /></div>
                    <HowItWorks id="roi_time" />
                </div>

                <div className="rounded-xl border border-[var(--accent)]/30 bg-[var(--accent)]/5 p-6">
                    <div className="flex items-center gap-2 text-[var(--accent)] mb-2">
                        <TrendingUp className="w-4 h-4" />
                        <p className="text-xs uppercase tracking-widest">Profit captured</p>
                    </div>
                    <p className="text-3xl font-black text-[#e5e5e5]">{formatKES(mc.monthly_impact_cents)}</p>
                    <p className="text-[#525252] text-sm mt-1">
                        from {mc.recommendations_approved} approved pricing recommendation
                        {mc.recommendations_approved === 1 ? "" : "s"}
                    </p>
                    <div className="mt-1"><TrendChip pct={mc.change_pct} /></div>
                    {!!mc.all_time_approved && mc.all_time_monthly_impact_cents !== undefined && (
                        <p className="text-[11px] text-[#525252] mt-2 pt-2 border-t border-[var(--accent)]/15">
                            All-time: <span className="text-[#a3a3a3]">{formatKES(mc.all_time_monthly_impact_cents)}/mo</span> standing uplift from {mc.all_time_approved} approved change{mc.all_time_approved === 1 ? "" : "s"}
                        </p>
                    )}
                    <HowItWorks id="roi_captured" />
                </div>

                <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-6">
                    <div className="flex items-center gap-2 text-amber-400 mb-2">
                        <Target className="w-4 h-4" />
                        <p className="text-xs uppercase tracking-widest">Opportunities flagged</p>
                    </div>
                    <p className="text-3xl font-black text-[#e5e5e5]">{formatKES(oppsTotal)}</p>
                    <p className="text-[#525252] text-sm mt-1">not yet acted on</p>
                    <HowItWorks id="roi_opportunities" />
                </div>
            </div>

            {/* Net ROI — the "is it worth what it costs?" answer. Only shown once
                there's metered AI spend to divide by; otherwise it would be a
                divide-by-zero dressed up as a number. */}
            {econ && econ.roi_multiple !== null && econ.roi_multiple !== undefined && (
                <div className="rounded-xl border border-[var(--accent)]/30 bg-gradient-to-br from-[var(--accent)]/[0.07] to-transparent p-5">
                    <div className="flex items-center gap-2 text-[var(--accent)] mb-2">
                        <Scale className="w-4 h-4" />
                        <p className="text-xs uppercase tracking-widest">Net return on your AI</p>
                    </div>
                    <div className="flex flex-wrap items-end gap-x-4 gap-y-1">
                        <p className="text-3xl font-black text-[#e5e5e5]">
                            {econ.roi_multiple}× <span className="text-base font-bold text-[#737373]">return</span>
                        </p>
                        <p className="text-[#a3a3a3] text-sm mb-1">
                            Every <span className="text-[#e5e5e5] font-medium">{formatKES(100)}</span> spent on AI returned{" "}
                            <span className="text-emerald-400 font-medium">{formatKES(Math.round(econ.roi_multiple * 100))}</span> in value.
                        </p>
                    </div>
                    <p className="text-[11px] text-[#525252] mt-2">
                        {formatKES(econ.value_delivered_cents)} value delivered (time saved + profit captured) vs{" "}
                        {formatKES(econ.ai_cost_cents)} in AI cost, last {days} days. Opportunities not yet captured are excluded — this counts only real money.
                    </p>
                    <HowItWorks id="roi_net" />
                </div>
            )}

            {/* Grounded AI reading (same trust badge as the AI Command Center) */}
            <NarrativeBlock n={data!.narrative} />

            {/* Time-saved breakdown */}
            <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
                <p className="text-[#e5e5e5] font-semibold text-sm mb-1">
                    Where the {ts.hours_saved_30d} hours came from
                </p>
                <p className="text-[#525252] text-xs mb-4">
                    Each row is work the AI did automatically. Hover the info dot to see what a
                    staff member would have done by hand.
                </p>
                {ts.breakdown.length === 0 ? (
                    <p className="text-[#525252] text-sm">No automated activity in this window.</p>
                ) : (
                    <div className="space-y-2">
                        {ts.breakdown.map((b, i) => (
                            <div key={i} className="flex items-center justify-between text-sm py-2 border-b border-[#1a1a1a] last:border-0 gap-3">
                                <span className="text-[#a3a3a3] flex items-center gap-1.5 min-w-0">
                                    <span className="truncate">{CATEGORY_LABELS[b.category] || b.category}</span>
                                    {CATEGORY_WHY[b.category] && (
                                        <span title={CATEGORY_WHY[b.category]} className="flex-shrink-0">
                                            <Info className="w-3 h-3 text-[#525252]" />
                                        </span>
                                    )}
                                    <span className="text-[#525252] whitespace-nowrap"> · {b.count}× at {b.minutes_per_action} min</span>
                                </span>
                                <span className="text-[#e5e5e5] font-medium whitespace-nowrap">{Math.round(b.total_minutes / 60 * 10) / 10} hrs</span>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Opportunities breakdown */}
            {opps.length > 0 && (
                <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
                    <p className="text-[#e5e5e5] font-semibold text-sm mb-1">Money on the table the AI has found</p>
                    <p className="text-[#525252] text-xs mb-4">Flagged but not yet acted on — approve or action these to capture it.</p>
                    <div className="space-y-3">
                        {opps.map((o, i) => (
                            <div key={i} className="py-2 border-b border-[#1a1a1a] last:border-0">
                                <div className="flex items-center justify-between text-sm gap-3">
                                    <span className="text-[#a3a3a3]">{o.label}</span>
                                    <span className="text-amber-400 font-medium whitespace-nowrap">{formatKES(o.monthly_value_cents)}/mo</span>
                                </div>
                                {OPP_SOURCE_EXPLAIN[o.source] && (
                                    <p className="text-[11px] text-[#525252] mt-1">{OPP_SOURCE_EXPLAIN[o.source]}</p>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Kitchen capacity — non-monetary "do more with the same staff" story */}
            {cap && (
                <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
                    <div className="flex items-center gap-2 text-[#e5e5e5] mb-1">
                        <ChefHat className="w-4 h-4 text-[var(--accent)]" />
                        <p className="font-semibold text-sm">Kitchen capacity</p>
                    </div>
                    <p className="text-[#525252] text-xs mb-2">
                        Serve more covers with the same staff — not counted as money above.
                    </p>
                    <HowItWorks id="roi_capacity" />
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
                        <div>
                            <p className="text-2xl font-bold text-[#e5e5e5]">{cap.avg_order_minutes}<span className="text-sm text-[#525252]"> min</span></p>
                            <p className="text-[#525252] text-xs mt-1">avg order time</p>
                        </div>
                        <div>
                            <p className="text-2xl font-bold text-[#e5e5e5]">{cap.orders_per_day}</p>
                            <p className="text-[#525252] text-xs mt-1">orders / day</p>
                        </div>
                        <div>
                            <p className="text-2xl font-bold text-[#e5e5e5]">{cap.bottlenecks_found}</p>
                            <p className="text-[#525252] text-xs mt-1">bottlenecks flagged</p>
                        </div>
                        <div>
                            <p className="text-2xl font-bold text-[#e5e5e5]">{cap.reclaimable_delay_minutes}<span className="text-sm text-[#525252]"> min</span></p>
                            <p className="text-[#525252] text-xs mt-1">reclaimable delay</p>
                        </div>
                    </div>
                </div>
            )}

            {/* Annual run-rate — a simple ×12 projection of the two monthly money
                figures. Framed as "at the current pace", never a guarantee. */}
            {proj && (proj.annual_money_saved_cents > 0 || proj.annual_captured_cents > 0) && (
                <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
                    <div className="flex items-center gap-2 text-[#e5e5e5] mb-1">
                        <CalendarClock className="w-4 h-4 text-[var(--accent)]" />
                        <p className="font-semibold text-sm">At this pace, over a year</p>
                    </div>
                    <p className="text-[#525252] text-xs mb-4">
                        A straight projection of your current monthly savings — shown to size the opportunity, not as a promise.
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                        <div>
                            <p className="text-2xl font-bold text-[#e5e5e5]">{proj.annual_hours_saved.toLocaleString()}<span className="text-sm text-[#525252]"> hrs</span></p>
                            <p className="text-[#525252] text-xs mt-1">staff time saved / year</p>
                        </div>
                        <div>
                            <p className="text-2xl font-bold text-emerald-400">{formatKES(proj.annual_money_saved_cents)}</p>
                            <p className="text-[#525252] text-xs mt-1">labour value / year</p>
                        </div>
                        <div>
                            <p className="text-2xl font-bold text-[var(--accent)]">{formatKES(proj.annual_captured_cents)}</p>
                            <p className="text-[#525252] text-xs mt-1">captured profit / year</p>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
