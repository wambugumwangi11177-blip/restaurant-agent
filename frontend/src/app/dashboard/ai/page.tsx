"use client";

/**
 * /dashboard/ai — AI Command Center
 *
 * Replaced, and as of 2026-07-08 fully deleted, two earlier attempts:
 * /dashboard/insights (hardcoded Lavy demo) and /ai-dashboard (raw fetch, its
 * own layout, and broken against the live API — it read `data.restaurant.name`
 * from /ai/dashboard, which returns no `restaurant` key, and its pricing
 * "Apply" posted a menu-item id to a route keyed on recommendation id).
 * Nothing linked to either, yet both shipped in every `next build`.
 *
 * This page:
 *   - Lives inside the main dashboard layout (same sidebar/nav as POS, Kitchen etc)
 *   - Uses the shared api.ts axios client (automatic auth, 401 redirect, base URL)
 *   - Shows REAL data from the backend AI agents
 *   - Falls back to a helpful empty state (not fake Lavy data) for new restaurants
 */

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import {
    Brain, TrendingUp, AlertTriangle, CheckCircle,
    RefreshCw, Zap, Shield, Activity, ArrowRight,
    Sparkles, ShieldCheck, ShieldAlert, Info, ChevronDown,
} from "lucide-react";
import Link from "next/link";

// Mirrors the actual shape returned by ai/ops_manager.get_operations_dashboard
// (served via GET /ai/dashboard) — this page previously assumed field names
// (revenue_today_kes, total_revenue_30d_kes, restaurant.name, etc.) that the
// backend never returned, which threw a TypeError on `data!.restaurant.name`
// the instant the page rendered. Found 2026-07-07 from a user report ("AI
// page brings an error message").
interface DashboardData {
    health_score: number;
    health_breakdown: { category: string; score: number; weight: number; detail: string }[];
    quick_stats: {
        today_orders: number;
        today_revenue: number;
        yesterday_revenue: number;
        day_over_day_change: number;
        pending_orders: number;
        menu_items: number;
        total_revenue_30d: number;
        avg_order_value: number;
        active_alerts: number;
    };
    risks: { severity: string; risk: string; detail: string }[];
    opportunities: { opportunity: string; potential: string; detail: string }[];
    ai_modules: { revenue?: { week_over_week_growth?: number } };
    recent_ai_actions: { action: string; agent: string; time: string }[];
}

function formatKES(cents: number) {
    if (!cents) return "KES 0";
    return `KES ${(cents / 100).toLocaleString("en-KE", { maximumFractionDigits: 0 })}`;
}

const healthColor = (score: number) =>
    score >= 75 ? "text-emerald-400" : score >= 50 ? "text-amber-400" : "text-red-400";

const healthBg = (score: number) =>
    score >= 75
        ? "border-emerald-500/30 bg-emerald-500/5"
        : score >= 50
        ? "border-amber-500/30 bg-amber-500/5"
        : "border-red-500/30 bg-red-500/5";

const barColor = (score: number) =>
    score >= 70 ? "bg-emerald-400" : score >= 50 ? "bg-amber-400" : "bg-red-400";

const severityStyle: Record<string, string> = {
    CRITICAL: "border-red-500/30 bg-red-500/10 text-red-300",
    HIGH: "border-orange-500/30 bg-orange-500/10 text-orange-300",
    MEDIUM: "border-amber-500/30 bg-amber-500/10 text-amber-300",
};

function EmptyState({ restaurantName }: { restaurantName: string }) {
    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-[#e5e5e5]">AI Command Center</h1>
                <p className="text-[#525252] mt-1 text-sm">{restaurantName} — Getting started</p>
            </div>
            <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-8 text-center space-y-4">
                <Brain className="w-12 h-12 text-[#d4a853] mx-auto" />
                <h2 className="text-[#e5e5e5] font-semibold text-lg">Your AI agents are ready</h2>
                <p className="text-[#525252] text-sm max-w-md mx-auto">
                    Add menu items, record some orders, and your AI agents will start generating
                    real insights — pricing recommendations, inventory alerts, revenue forecasts.
                </p>
                <div className="flex flex-wrap gap-3 justify-center pt-2">
                    <Link
                        href="/dashboard/menu"
                        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[#d4a853] text-[#0a0a0a] font-semibold text-sm hover:bg-[#e0b96a] transition-colors"
                    >
                        Add menu items <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                    <Link
                        href="/dashboard/pos"
                        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[#141414] border border-[#262626] text-[#e5e5e5] text-sm hover:bg-[#1a1a1a] transition-colors"
                    >
                        Record first order
                    </Link>
                </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {[
                    { icon: TrendingUp, label: "Pricing Intelligence", desc: "Surge pricing, margin alerts, delivery gap analysis" },
                    { icon: Shield, label: "Stock Monitoring", desc: "Predictive restock alerts before you run out" },
                    { icon: Activity, label: "Revenue Forecasting", desc: "7-day and 30-day predictions with confidence bands" },
                ].map((agent) => (
                    <div key={agent.label} className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
                        <agent.icon className="w-5 h-5 text-[#d4a853] mb-3" />
                        <p className="text-[#e5e5e5] font-medium text-sm">{agent.label}</p>
                        <p className="text-[#525252] text-xs mt-1">{agent.desc}</p>
                    </div>
                ))}
            </div>
        </div>
    );
}

export default function AiDashboard() {
    const { user } = useAuth();
    const [data, setData] = useState<DashboardData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

    const restaurantName = (user as any)?.restaurant_name || "Your Restaurant";

    const fetchData = async () => {
        setLoading(true);
        setError("");
        try {
            const res = await api.get("/ai/dashboard");
            setData(res.data);
            setLastUpdated(new Date());
        } catch (e: any) {
            setError(e?.response?.data?.detail || e?.message || "Could not load AI data");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchData(); }, []);

    if (loading) {
        return (
            <div className="space-y-4">
                <div className="bg-[#141414] rounded-xl h-8 w-48 animate-pulse" />
                <div className="bg-[#141414] rounded-xl h-40 animate-pulse" />
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                    {[...Array(4)].map((_, i) => (
                        <div key={i} className="bg-[#141414] rounded-xl h-20 animate-pulse" />
                    ))}
                </div>
            </div>
        );
    }

    // No data or genuinely empty restaurant → helpful onboarding empty state.
    // Was keyed on today_orders === 0, which is wrong for any restaurant whose
    // live order flow has gone quiet (or whose historical data doesn't extend
    // into "today") — same class of bug as the main dashboard's demo-data
    // fallback. Use actual setup/activity signals instead.
    const isNewRestaurant = !data || (!data.quick_stats.menu_items && !data.quick_stats.total_revenue_30d);
    if (isNewRestaurant && !error) {
        return <EmptyState restaurantName={restaurantName} />;
    }

    if (error) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[50vh] space-y-4">
                <AlertTriangle className="w-10 h-10 text-amber-400" />
                <p className="text-[#e5e5e5] font-medium">Could not load AI data</p>
                <p className="text-[#525252] text-sm text-center max-w-sm">{error}</p>
                <button
                    onClick={fetchData}
                    className="px-4 py-2 bg-[#d4a853] text-[#0a0a0a] font-semibold rounded-lg text-sm hover:bg-[#e0b96a]"
                >
                    Retry
                </button>
            </div>
        );
    }

    const hs = data!.health_score;
    const qs = data!.quick_stats;
    const wowGrowth = data!.ai_modules?.revenue?.week_over_week_growth ?? qs.day_over_day_change;

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-start justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-[#e5e5e5]">AI Command Center</h1>
                    <p className="text-[#525252] mt-1 text-sm">
                        {restaurantName} — Real-time intelligence
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

            {/* Health Score */}
            <div className={`rounded-xl border p-6 ${healthBg(hs)}`}>
                <div className="flex items-center justify-between">
                    <div>
                        <p className="text-[#525252] text-xs uppercase tracking-widest mb-1">System Health</p>
                        <p className={`text-6xl font-black ${healthColor(hs)}`}>{hs}</p>
                        <p className="text-[#525252] text-xs mt-2">
                            WoW Revenue:{" "}
                            <span className={wowGrowth >= 0 ? "text-emerald-400" : "text-red-400"}>
                                {wowGrowth >= 0 ? "+" : ""}
                                {wowGrowth}%
                            </span>
                        </p>
                        <HowItWorks id="health" />
                    </div>
                    <div className="space-y-2 min-w-[180px]">
                        {data!.health_breakdown.map((b, i) => (
                            <div key={i}>
                                <div className="flex justify-between text-xs text-[#525252] mb-1">
                                    <span>{b.category}</span>
                                    <span>{b.score}</span>
                                </div>
                                <div className="w-full bg-[#1a1a1a] rounded-full h-1.5">
                                    <div
                                        className={`h-1.5 rounded-full transition-all ${barColor(b.score)}`}
                                        style={{ width: `${b.score}%` }}
                                    />
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Quick stats */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                {[
                    { label: "Today's Revenue", value: formatKES(qs.today_revenue) },
                    { label: "Orders Today", value: String(qs.today_orders) },
                    { label: "Active Alerts", value: String(qs.active_alerts) },
                    { label: "30-Day Revenue", value: formatKES(qs.total_revenue_30d) },
                ].map((stat) => (
                    <div key={stat.label} className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-4">
                        <p className="text-xs text-[#525252] mb-1">{stat.label}</p>
                        <p className="text-xl font-bold text-[#e5e5e5]">{stat.value}</p>
                    </div>
                ))}
            </div>

            {/* Concrete, prioritised actions to raise the health score */}
            <HealthBoostSection breakdown={data!.health_breakdown} score={hs} />

            {/* AI modules — inline, not separate pages. These used to link to
                /dashboard/ai/pricing, /dashboard/ai/labor, /dashboard/ai/menu,
                none of which exist (a 404 on every click) — found 2026-07-07
                from a user report. Each section fetches and renders itself
                independently, so one module erroring doesn't take down the
                others or force a page navigation to see what's wrong. */}
            <ProfitSection />
            <PricingSection />
            <MenuEngineeringSection />
            <LaborSection />
            <DataQualitySection />

            {/* Risks + Opportunities */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Risks */}
                <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
                    <h2 className="text-sm font-semibold text-[#e5e5e5] mb-4 flex items-center gap-2">
                        <AlertTriangle className="w-4 h-4 text-red-400" />
                        Active Risks ({data!.risks.length})
                    </h2>
                    {data!.risks.length === 0 ? (
                        <div className="flex items-center gap-2 text-emerald-400 text-sm py-2">
                            <CheckCircle className="w-4 h-4" />
                            No active risks
                        </div>
                    ) : (
                        <div className="space-y-2">
                            {data!.risks.slice(0, 5).map((r, i) => (
                                <div key={i} className={`p-3 rounded-lg border text-sm ${severityStyle[r.severity] || "border-[#262626] text-[#737373]"}`}>
                                    <p className="font-medium">{r.risk}</p>
                                    <p className="text-xs opacity-70 mt-0.5">{r.detail}</p>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Opportunities */}
                <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
                    <h2 className="text-sm font-semibold text-[#e5e5e5] mb-4 flex items-center gap-2">
                        <TrendingUp className="w-4 h-4 text-emerald-400" />
                        Opportunities
                    </h2>
                    {data!.opportunities.length === 0 ? (
                        <p className="text-[#525252] text-sm py-2">No opportunities flagged yet — keep adding data</p>
                    ) : (
                        <div className="space-y-2">
                            {data!.opportunities.map((o, i) => (
                                <div key={i} className="p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
                                    <p className="text-sm font-medium text-[#e5e5e5]">{o.opportunity}</p>
                                    <p className="text-emerald-400 text-xs font-medium mt-0.5">{o.potential}</p>
                                    <p className="text-[#525252] text-xs">{o.detail}</p>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* Recent AI Actions */}
            <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
                <h2 className="text-sm font-semibold text-[#e5e5e5] mb-4 flex items-center gap-2">
                    <Zap className="w-4 h-4 text-[#d4a853]" />
                    Recent AI Actions
                </h2>
                {data!.recent_ai_actions.length === 0 ? (
                    <p className="text-[#525252] text-sm">No AI actions logged yet</p>
                ) : (
                    <div className="space-y-2">
                        {data!.recent_ai_actions.map((log, i) => (
                            <div key={i} className="flex justify-between items-center py-2 border-b border-[#1a1a1a] last:border-0">
                                <div>
                                    <p className="text-sm text-[#e5e5e5]">{log.action}</p>
                                    <p className="text-xs text-[#525252]">{log.agent}</p>
                                </div>
                                <span className="text-xs text-[#525252] bg-[#141414] px-2 py-1 rounded-md whitespace-nowrap">{log.time}</span>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

/* ── Plain-language explanations ───────────────────────────────────────────
   Every AI module speaks analyst jargon a normal restaurant owner/staff won't
   recognise ("contribution margin", "velocity ratio", "Plowhorse"). This is the
   translation layer: what each brain does, where its numbers come from, and what
   every term means — in plain language. Definitions are kept faithful to the
   backend that computes them (e.g. popularity index = 0.7x average in
   ai/menu_engineer.py; 40% margin floor / 35% food-cost ceiling in
   ai/pricing/analysis.py). This is static copy — it invents no numbers, so the
   server-side grounding guarantee (ai/reasoning/narrator.py) is untouched. */
interface Explainer {
    what: string;
    where: string;
    caveat?: string;
    terms: { t: string; d: string }[];
}

const AI_EXPLAIN: Record<string, Explainer> = {
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
};

function HowItWorks({ id }: { id: keyof typeof AI_EXPLAIN }) {
    const [open, setOpen] = useState(false);
    const e = AI_EXPLAIN[id];
    if (!e) return null;
    return (
        <div className="mt-1">
            <button
                onClick={() => setOpen((v) => !v)}
                className="flex items-center gap-1 text-[11px] text-[#737373] hover:text-[#d4a853] transition-colors"
            >
                <Info className="w-3 h-3" />
                <span>How this works</span>
                <ChevronDown className={`w-3 h-3 transition-transform ${open ? "rotate-180" : ""}`} />
            </button>
            {open && (
                <div className="mt-2 rounded-lg border border-[#1a1a1a] bg-[#0a0a0a] p-3 space-y-2.5">
                    <p className="text-xs text-[#a3a3a3] leading-relaxed">{e.what}</p>
                    <p className="text-[11px] text-[#525252]">
                        <span className="text-[#737373] font-medium">Where this comes from:</span> {e.where}
                    </p>
                    {e.caveat && (
                        <p className="text-[11px] text-amber-400/80 flex gap-1.5">
                            <AlertTriangle className="w-3 h-3 flex-shrink-0 mt-0.5" />
                            <span>{e.caveat}</span>
                        </p>
                    )}
                    <div className="pt-1 border-t border-[#1a1a1a] space-y-1.5">
                        <p className="text-[10px] uppercase tracking-wide text-[#525252] font-semibold">What the words mean</p>
                        {e.terms.map((term) => (
                            <p key={term.t} className="text-[11px] text-[#737373] leading-snug">
                                <span className="text-[#e5e5e5] font-medium">{term.t}</span> — {term.d}
                            </p>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

// On-demand "Explain this to me": sends one insight to the grounded reasoning
// layer (POST /ai/explain) and shows a plain-language paragraph. Degrades quietly
// when no LLM provider is configured (available:false → a short notice).
function ExplainButton({ item, label }: { item: Record<string, any>; label?: string }) {
    const [state, setState] = useState<"idle" | "loading" | "done" | "none">("idle");
    const [text, setText] = useState("");

    const explain = async () => {
        if (state === "loading") return;
        setState("loading");
        try {
            const res = await api.post("/ai/explain", { item, label });
            if (res.data?.available && res.data.explanation) {
                const n = res.data.explanation;
                const extra = (n.actions || []).slice(0, 1).map((a: any) => a.action).join(" ");
                setText([n.headline, extra].filter(Boolean).join(" — "));
                setState("done");
            } else {
                setState("none");
            }
        } catch {
            setState("none");
        }
    };

    if (state === "done") {
        return <p className="text-[11px] text-[#a3a3a3] mt-1 leading-relaxed bg-[#0a0a0a] border border-[#1a1a1a] rounded-md p-2">{text}</p>;
    }
    if (state === "none") {
        return <p className="text-[11px] text-[#525252] mt-1 italic">Plain-language explainer isn’t available right now.</p>;
    }
    return (
        <button
            onClick={explain}
            disabled={state === "loading"}
            className="mt-1 flex items-center gap-1 text-[11px] text-[#737373] hover:text-[#d4a853] transition-colors disabled:opacity-60"
        >
            <Info className="w-3 h-3" />
            {state === "loading" ? "Explaining…" : "Explain this to me"}
        </button>
    );
}

/* ── Inline AI module sections ─────────────────────────────────────────── */

function ModuleShell({
    icon: Icon, title, subtitle, explainKey, loading, error, onRetry, children,
}: {
    icon: any; title: string; subtitle?: string; explainKey?: keyof typeof AI_EXPLAIN; loading: boolean; error: string; onRetry: () => void; children: React.ReactNode;
}) {
    return (
        <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
            <h2 className="text-sm font-semibold text-[#e5e5e5] flex items-center gap-2">
                <Icon className="w-4 h-4 text-[#d4a853]" />
                {title}
            </h2>
            {subtitle && <p className="text-xs text-[#525252] mt-1">{subtitle}</p>}
            {explainKey && <HowItWorks id={explainKey} />}
            <div className="mb-4" />
            {loading ? (
                <div className="space-y-2">
                    <div className="bg-[#141414] rounded-lg h-16 animate-pulse" />
                </div>
            ) : error ? (
                <div className="flex items-center justify-between gap-3 py-2">
                    <p className="text-[#525252] text-sm">{error}</p>
                    <button onClick={onRetry} className="text-xs text-[#d4a853] hover:underline flex-shrink-0">Retry</button>
                </div>
            ) : (
                children
            )}
        </div>
    );
}

function useAiModule<T>(endpoint: string) {
    const [data, setData] = useState<T | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    const fetchData = async () => {
        setLoading(true);
        setError("");
        try {
            const res = await api.get(endpoint);
            // _safe_run on the backend returns 200 with {error, available:false}
            // on internal failure rather than an HTTP error status — surface
            // that as a real error here instead of rendering undefined fields.
            if (res.data && res.data.available === false) {
                setError(res.data.error || "This module hit an error analysing your data");
            } else {
                setData(res.data);
            }
        } catch (e: any) {
            setError(e?.response?.data?.detail || e?.message || "Could not load this module");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchData(); }, [endpoint]);

    return { data, loading, error, retry: fetchData };
}

function PricingSection() {
    interface PricingData {
        summary: { surge_opportunities: number; reprice_needed: number; stimulate_candidates: number; total_revenue_opportunity_cents: number; items_analysed: number };
        recommendations: { item_id: number; item_name: string; type: string; current_price: number; suggested_price: number; monthly_impact_cents: number; reason: string; data_days?: number; has_velocity_data?: boolean }[];
        narrative?: Narrative;
    }
    const { data, loading, error, retry } = useAiModule<PricingData>("/ai/pricing");

    return (
        <ModuleShell icon={TrendingUp} title="Pricing Intelligence" explainKey="pricing" loading={loading} error={error} onRetry={retry}>
            {data && (
                <>
                    <NarrativeBlock n={data.narrative} />
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                        <MiniStat label="Surge" value={data.summary.surge_opportunities} />
                        <MiniStat label="Reprice" value={data.summary.reprice_needed} />
                        <MiniStat label="Stimulate" value={data.summary.stimulate_candidates} />
                        <MiniStat label="Opportunity" value={formatKES(data.summary.total_revenue_opportunity_cents)} />
                    </div>
                    {data.recommendations.length === 0 ? (
                        <p className="text-[#525252] text-sm">No pricing changes recommended right now — {data.summary.items_analysed} items analysed.</p>
                    ) : (
                        <div className="space-y-2">
                            {data.recommendations.slice(0, 5).map((r) => {
                                // "Early signal" badge: pricing needs 14+ days of history before it
                                // trusts demand-based moves (SURGE/STIMULATE). has_velocity_data=false
                                // (or data_days < 14) means treat this as a lighter signal.
                                const earlySignal = r.has_velocity_data === false || (typeof r.data_days === "number" && r.data_days < 14);
                                return (
                                    <div key={r.item_id} className="flex items-center justify-between py-2 border-b border-[#1a1a1a] last:border-0 text-sm gap-3">
                                        <div className="min-w-0">
                                            <div className="flex items-center gap-2 flex-wrap">
                                                <p className="text-[#e5e5e5]">{r.item_name}</p>
                                                {/* Worked example in the owner's own numbers */}
                                                <span className="text-[11px] text-[#737373] whitespace-nowrap">
                                                    KES {(r.current_price / 100).toLocaleString()} → <span className="text-[#d4a853]">KES {(r.suggested_price / 100).toLocaleString()}</span>
                                                </span>
                                                {earlySignal && (
                                                    <span
                                                        className="text-[9px] font-medium uppercase tracking-wide px-1.5 py-0.5 rounded bg-[#3b82f6]/10 text-[#60a5fa] whitespace-nowrap"
                                                        title={typeof r.data_days === "number" ? `Only ${r.data_days} days of data so far` : "Limited history — treat as an early signal"}
                                                    >
                                                        early signal
                                                    </span>
                                                )}
                                            </div>
                                            <p className="text-xs text-[#525252] mt-0.5">{r.reason}</p>
                                            <ExplainButton item={r} label={`Pricing ${r.type} for ${r.item_name}`} />
                                        </div>
                                        <span className="text-emerald-400 text-xs font-medium whitespace-nowrap">+{formatKES(r.monthly_impact_cents)}/mo</span>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </>
            )}
        </ModuleShell>
    );
}

function LaborSection() {
    interface LaborData {
        summary: { total_labor_cost_30d: number; labor_pct: number; labor_status: string; sales_per_hour: number; overtime_cost_30d: number };
        recommendations: { priority: string; message: string; action: string }[];
    }
    const { data, loading, error, retry } = useAiModule<LaborData>("/ai/labor");

    return (
        <ModuleShell icon={Activity} title="Labor Optimization" explainKey="labor" loading={loading} error={error} onRetry={retry}>
            {data && (
                <>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                        <MiniStat label="Labor Cost (30d)" value={formatKES(data.summary.total_labor_cost_30d)} />
                        <MiniStat label="Labor %" value={`${data.summary.labor_pct}%`} tone={data.summary.labor_status === "HIGH" ? "warn" : "ok"} />
                        <MiniStat label="Sales/Hour" value={formatKES(data.summary.sales_per_hour)} />
                        <MiniStat label="Overtime Cost" value={formatKES(data.summary.overtime_cost_30d)} />
                    </div>
                    {data.recommendations.length === 0 ? (
                        <p className="text-[#525252] text-sm">Staffing looks well balanced.</p>
                    ) : (
                        <div className="space-y-2">
                            {data.recommendations.slice(0, 4).map((r, i) => (
                                <div key={i} className="p-3 rounded-lg bg-[#141414] border border-[#1a1a1a] text-sm">
                                    <p className="text-[#e5e5e5]">{r.message}</p>
                                    {r.action && <p className="text-xs text-[#d4a853] mt-1">💡 {r.action}</p>}
                                </div>
                            ))}
                        </div>
                    )}
                </>
            )}
        </ModuleShell>
    );
}

// Cost-price data-quality guard. Every profit/pricing figure divides by cost_price;
// this surfaces the items silently breaking those numbers so the owner fixes the
// input, not the output. Backed by GET /ai/data-quality (ai/data_quality.py).
const DQ_ISSUE_LABEL: Record<string, string> = {
    MISSING_COST: "No cost price set",
    MISSING_PRICE: "No sale price set",
    SELLING_AT_LOSS: "Sold at a loss",
    SUSPICIOUSLY_LOW_COST: "Cost looks like a typo",
    THIN_MARGIN: "Very thin margin",
};

function DataQualitySection() {
    interface DQData {
        summary: { total_items: number; items_with_issues: number; missing_cost_count: number; coverage_pct: number; high_severity_count: number };
        issues: { item_id: number; item_name: string; category: string; price: number; cost_price: number; qty_30d: number; issue: string; severity: string; explanation: string }[];
    }
    const { data, loading, error, retry } = useAiModule<DQData>("/ai/data-quality");

    return (
        <ModuleShell icon={Shield} title="Cost-Price Data Check" explainKey="dataquality" loading={loading} error={error} onRetry={retry}
            subtitle="Your profit & pricing numbers are only as accurate as the cost prices you enter — this flags the gaps.">
            {data && (
                <>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                        <MiniStat label="Cost-price coverage" value={`${data.summary.coverage_pct}%`} tone={data.summary.coverage_pct >= 90 ? "ok" : "warn"} />
                        <MiniStat label="Items to fix" value={data.summary.items_with_issues} tone={data.summary.items_with_issues > 0 ? "warn" : "ok"} />
                        <MiniStat label="Missing cost" value={data.summary.missing_cost_count} tone={data.summary.missing_cost_count > 0 ? "warn" : "ok"} />
                        <MiniStat label="High severity" value={data.summary.high_severity_count} tone={data.summary.high_severity_count > 0 ? "warn" : "ok"} />
                    </div>
                    {data.issues.length === 0 ? (
                        <p className="text-emerald-400 text-sm flex items-center gap-2">
                            <CheckCircle className="w-4 h-4" /> Cost prices look healthy — your profit numbers can be trusted.
                        </p>
                    ) : (
                        <div className="space-y-2">
                            {data.issues.slice(0, 6).map((i) => (
                                <div key={i.item_id} className="p-3 rounded-lg bg-[#141414] border border-[#1a1a1a] text-sm">
                                    <div className="flex items-center justify-between gap-2">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${i.severity === "HIGH" ? "bg-red-500/10 text-red-400" : i.severity === "MEDIUM" ? "bg-amber-500/10 text-amber-400" : "bg-[#3b82f6]/10 text-[#60a5fa]"}`}>{DQ_ISSUE_LABEL[i.issue] || i.issue}</span>
                                            <p className="text-[#e5e5e5]">{i.item_name}</p>
                                        </div>
                                        {i.qty_30d > 0 && <span className="text-xs text-[#525252] whitespace-nowrap">{i.qty_30d} sold/30d</span>}
                                    </div>
                                    <p className="text-xs text-[#525252] mt-1">{i.explanation}</p>
                                </div>
                            ))}
                            <Link href="/dashboard/menu" className="inline-flex items-center gap-1 text-xs text-[#d4a853] hover:underline mt-1">
                                Fix in Menu <ArrowRight className="w-3 h-3" />
                            </Link>
                        </div>
                    )}
                </>
            )}
        </ModuleShell>
    );
}

// The Star/Plowhorse/Puzzle/Dog quadrants explained in plain language, so a
// non-analyst owner understands what the classification means and what to do.
const MENU_CLASS = {
    Stars: { tone: "ok" as const, blurb: "Popular AND high-margin — your winners. Keep them prominent and never 86 them." },
    Plowhorses: { tone: undefined, blurb: "Popular but low-margin. Nudge price up or trim portion cost — small changes, big impact." },
    Puzzles: { tone: undefined, blurb: "High-margin but under-ordered. Promote, reposition on the menu, or add to upsell prompts." },
    Dogs: { tone: "warn" as const, blurb: "Low popularity and low margin. Rework the recipe or remove to free up menu space." },
};

function MenuEngineeringSection() {
    interface MenuData {
        summary: { total_items: number; stars: number; plowhorses: number; puzzles: number; dogs: number; avg_food_cost_pct: number; menu_optimization_score?: number };
        category_performance: { category: string; revenue_share_pct: number; avg_margin_pct: number; item_count: number }[];
        recommendations: { item: string; action: string; reason: string; priority: string; impact: string }[];
        narrative?: Narrative;
    }
    const { data, loading, error, retry } = useAiModule<MenuData>("/ai/menu-engineering");

    return (
        <ModuleShell icon={Brain} title="Menu Engineering" explainKey="menu" loading={loading} error={error} onRetry={retry}
            subtitle="Classifies every dish by popularity × profit so you know what to promote, reprice, or cut.">
            {data && (
                <>
                    <NarrativeBlock n={data.narrative} />
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
                        {([["Stars", data.summary.stars], ["Plowhorses", data.summary.plowhorses],
                          ["Puzzles", data.summary.puzzles], ["Dogs", data.summary.dogs]] as const).map(([k, v]) => (
                            <div key={k} className="rounded-lg bg-[#141414] border border-[#1a1a1a] p-3">
                                <div className="flex items-center justify-between">
                                    <p className="text-xs text-[#525252]">{k}</p>
                                    <p className={`text-sm font-bold ${MENU_CLASS[k].tone === "ok" ? "text-emerald-400" : MENU_CLASS[k].tone === "warn" ? "text-red-400" : "text-[#e5e5e5]"}`}>{v}</p>
                                </div>
                                <p className="text-[10px] text-[#525252] mt-1 leading-snug">{MENU_CLASS[k].blurb}</p>
                            </div>
                        ))}
                    </div>

                    {data.category_performance && data.category_performance.length > 0 && (
                        <div className="mb-4">
                            <p className="text-xs font-semibold text-[#737373] mb-2">Category performance (share of revenue · margin)</p>
                            <div className="space-y-1.5">
                                {data.category_performance.slice(0, 6).map((c, i) => (
                                    <div key={i} className="flex items-center gap-2 text-xs">
                                        <span className="text-[#e5e5e5] w-24 flex-shrink-0 truncate">{c.category}</span>
                                        <div className="flex-1 h-1.5 bg-[#1a1a1a] rounded-full overflow-hidden">
                                            <div className="h-full bg-[#d4a853] rounded-full" style={{ width: `${Math.min(c.revenue_share_pct * 3, 100)}%` }} />
                                        </div>
                                        <span className="text-[#737373] w-10 text-right">{c.revenue_share_pct}%</span>
                                        <span className={`w-12 text-right ${c.avg_margin_pct >= 55 ? "text-emerald-400" : c.avg_margin_pct >= 40 ? "text-amber-400" : "text-red-400"}`}>{c.avg_margin_pct}%</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {data.recommendations && data.recommendations.length > 0 && (
                        <>
                            <p className="text-xs font-semibold text-[#737373] mb-2">Top menu actions</p>
                            <div className="space-y-2">
                                {data.recommendations.slice(0, 5).map((r, i) => (
                                    <div key={i} className="p-3 rounded-lg bg-[#141414] border border-[#1a1a1a] text-sm">
                                        <div className="flex items-center gap-2">
                                            <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${r.priority === "high" ? "bg-red-500/10 text-red-400" : r.priority === "medium" ? "bg-amber-500/10 text-amber-400" : "bg-[#3b82f6]/10 text-[#3b82f6]"}`}>{r.priority}</span>
                                            <p className="text-[#e5e5e5]">{r.item} — {r.action}</p>
                                        </div>
                                        <p className="text-xs text-[#525252] mt-1">{r.reason}</p>
                                        {r.impact && <p className="text-xs text-emerald-400 mt-0.5">📈 {r.impact}</p>}
                                    </div>
                                ))}
                            </div>
                        </>
                    )}
                </>
            )}
        </ModuleShell>
    );
}

function ProfitSection() {
    interface ProfitData {
        summary: { gross_margin_pct: number; food_cost_pct: number; food_cost_status: string; total_gross_profit_30d: number; profit_leaks_found: number; total_leak_amount: number; star_items: number; dog_items: number };
        profit_leaks: { item_name: string; current_margin_pct: number; food_cost_pct: number; monthly_leak_cents: number; severity: string; action: string }[];
        stars: string[];
        dogs: string[];
        narrative?: Narrative;
    }
    const { data, loading, error, retry } = useAiModule<ProfitData>("/ai/profit");

    return (
        <ModuleShell icon={TrendingUp} title="Profit Intelligence" explainKey="profit" loading={loading} error={error} onRetry={retry}
            subtitle="Where money leaks out — dishes sold below a healthy margin, and exactly how much each costs you per month.">
            {data && (
                <>
                    <NarrativeBlock n={data.narrative} />
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                        <MiniStat label="Gross Margin" value={`${data.summary.gross_margin_pct}%`} tone={data.summary.gross_margin_pct >= 55 ? "ok" : "warn"} />
                        <MiniStat label="Food Cost" value={`${data.summary.food_cost_pct}%`} tone={data.summary.food_cost_status === "HEALTHY" ? "ok" : "warn"} />
                        <MiniStat label="Gross Profit (30d)" value={formatKES(data.summary.total_gross_profit_30d)} tone="ok" />
                        <MiniStat label="Leaks Found" value={data.summary.profit_leaks_found} tone={data.summary.profit_leaks_found > 0 ? "warn" : "ok"} />
                    </div>
                    {data.summary.total_leak_amount > 0 && (
                        <div className="mb-4 p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
                            <p className="text-sm text-[#e5e5e5]">💰 Fixing the flagged items recovers about
                                <span className="text-emerald-400 font-bold"> {formatKES(data.summary.total_leak_amount)}/month</span>.</p>
                        </div>
                    )}
                    {data.profit_leaks && data.profit_leaks.length > 0 && (
                        <div className="space-y-2">
                            {data.profit_leaks.slice(0, 6).map((l, i) => (
                                <div key={i} className="p-3 rounded-lg bg-[#141414] border border-[#1a1a1a] text-sm">
                                    <div className="flex items-center justify-between gap-2">
                                        <div className="flex items-center gap-2">
                                            <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${l.severity === "HIGH" ? "bg-red-500/10 text-red-400" : "bg-amber-500/10 text-amber-400"}`}>{l.severity}</span>
                                            <p className="text-[#e5e5e5]">{l.item_name}</p>
                                        </div>
                                        <span className="text-red-400 text-xs font-medium whitespace-nowrap">-{formatKES(l.monthly_leak_cents)}/mo</span>
                                    </div>
                                    <p className="text-xs text-[#525252] mt-1">Margin {l.current_margin_pct}% · food cost {l.food_cost_pct}%</p>
                                    <p className="text-xs text-[#d4a853] mt-0.5">💡 {l.action}</p>
                                    <ExplainButton item={l} label={`Profit leak: ${l.item_name}`} />
                                </div>
                            ))}
                        </div>
                    )}
                </>
            )}
        </ModuleShell>
    );
}

// Turns the health breakdown into specific, prioritised "do this next" guidance.
const HEALTH_ADVICE: Record<string, (detail: string) => string> = {
    "Menu Health": () => "Rework or remove your 'Dog' items and reprice 'Plowhorses' — see Menu Engineering below. Fewer weak items lifts this fast.",
    "Revenue Trend": () => "Revenue is trending down week-over-week. Run a promo on slow days and push high-margin items to reverse it.",
    "Kitchen Efficiency": () => "Prep times are dragging on the flagged stations. Rebalance staff to the bottleneck stations during peak hours.",
    "Inventory Status": () => "Restock the low items and use up near-expiry stock first (FIFO) to clear spoilage-risk flags.",
    "Reservation Reliability": () => "Cut no-shows with SMS reminders and a small deposit on large parties — that lifts completion and recovers lost covers.",
};

function HealthBoostSection({ breakdown, score }: { breakdown: { category: string; score: number; detail: string }[]; score: number }) {
    const weak = breakdown.filter((b) => b.score < 70).sort((a, b) => a.score - b.score);
    return (
        <div className="rounded-xl border border-[#d4a853]/25 bg-[#d4a853]/[0.04] p-5">
            <h2 className="text-sm font-semibold text-[#e5e5e5] mb-1 flex items-center gap-2">
                <Zap className="w-4 h-4 text-[#d4a853]" />
                How to raise your health score ({score} → higher)
            </h2>
            <p className="text-xs text-[#525252] mb-4">Your biggest wins first — each item below is dragging the score and is fixable.</p>
            {weak.length === 0 ? (
                <p className="text-emerald-400 text-sm flex items-center gap-2"><CheckCircle className="w-4 h-4" /> Every area is healthy — nice work.</p>
            ) : (
                <div className="space-y-2">
                    {weak.map((b, i) => (
                        <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-[#0f0f0f] border border-[#1a1a1a]">
                            <span className={`text-xs font-bold w-9 text-center flex-shrink-0 rounded px-1 py-0.5 ${b.score < 40 ? "bg-red-500/10 text-red-400" : "bg-amber-500/10 text-amber-400"}`}>{b.score}</span>
                            <div>
                                <p className="text-sm text-[#e5e5e5] font-medium">{b.category} <span className="text-[#525252] font-normal">— {b.detail}</span></p>
                                <p className="text-xs text-[#d4a853] mt-1">→ {(HEALTH_ADVICE[b.category] || (() => "Review this area's details and act on the flagged items."))(b.detail)}</p>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

// Shape of the `narrative` block attached by the backend reasoning layer
// (ai/reasoning/narrator.py). The figures shown in each module are computed
// deterministically; this is the LLM's plain-language *interpretation* of them,
// with every number it cites already grounding-checked server-side.
interface Narrative {
    headline: string;
    priorities: string[];
    actions: { action: string; why?: string; impact?: string }[];
    verified: boolean;
    ungrounded_numbers: string[];
    cached?: boolean;
}

// Renders the AI interpretation with a trust badge. `verified` means every
// figure the model wrote was found in the real data; if not, the backend has
// already redacted the bad figures and we surface how many were removed — so
// the badge is an honest trust signal, not decoration.
function NarrativeBlock({ n }: { n?: Narrative }) {
    const [showTrust, setShowTrust] = useState(false);
    if (!n || (!n.headline && (!n.priorities || n.priorities.length === 0))) return null;
    const redacted = n.ungrounded_numbers?.length || 0;
    return (
        <div className="mb-4 rounded-lg border border-[#d4a853]/25 bg-[#d4a853]/[0.04] p-4">
            <div className="flex items-start justify-between gap-3 mb-2">
                <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-[#d4a853]" />
                    <span className="text-xs font-semibold uppercase tracking-wide text-[#d4a853]">AI reading</span>
                </div>
                {n.verified ? (
                    <span
                        className="flex items-center gap-1 text-[10px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded px-1.5 py-0.5 whitespace-nowrap"
                        title="Every figure cited was checked against your real numbers"
                    >
                        <ShieldCheck className="w-3 h-3" /> Figures checked
                    </span>
                ) : (
                    <span
                        className="flex items-center gap-1 text-[10px] text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded px-1.5 py-0.5 whitespace-nowrap"
                        title={`Unverified figure(s) removed: ${n.ungrounded_numbers.join(", ")}`}
                    >
                        <ShieldAlert className="w-3 h-3" /> {redacted} figure{redacted === 1 ? "" : "s"} removed
                    </span>
                )}
            </div>
            {n.headline && <p className="text-sm text-[#e5e5e5] leading-snug">{n.headline}</p>}
            {n.priorities && n.priorities.length > 0 && (
                <ul className="mt-2 space-y-1">
                    {n.priorities.map((p, i) => (
                        <li key={i} className="text-xs text-[#a3a3a3] flex gap-2">
                            <span className="text-[#d4a853] flex-shrink-0">•</span>
                            <span>{p}</span>
                        </li>
                    ))}
                </ul>
            )}
            {n.actions && n.actions.length > 0 && (
                <div className="mt-2 space-y-1">
                    {n.actions.slice(0, 3).map((a, i) => (
                        <p key={i} className="text-xs text-[#737373]">
                            <span className="text-[#e5e5e5]">→ {a.action}</span>
                            {a.why ? ` — ${a.why}` : ""}
                        </p>
                    ))}
                </div>
            )}
            <button
                onClick={() => setShowTrust((v) => !v)}
                className="mt-2 flex items-center gap-1 text-[10px] text-[#525252] italic hover:text-[#737373] transition-colors"
            >
                AI interpretation · the figures above are computed exactly, not by the AI.
                <ChevronDown className={`w-2.5 h-2.5 transition-transform ${showTrust ? "rotate-180" : ""}`} />
            </button>
            {showTrust && (
                <div className="mt-1.5 rounded-md border border-[#1a1a1a] bg-[#0a0a0a] p-2.5 space-y-1.5">
                    <p className="text-[11px] text-[#a3a3a3] leading-relaxed">
                        The "AI reading" is only the AI's opinion in words. Every number is calculated
                        exactly by the system — never made up by the AI.
                    </p>
                    <p className="text-[11px] text-[#737373] leading-snug flex gap-1.5">
                        <ShieldCheck className="w-3 h-3 flex-shrink-0 mt-0.5 text-emerald-400" />
                        <span><span className="text-[#e5e5e5] font-medium">Figures checked</span> — every number the AI wrote was found in your real data.</span>
                    </p>
                    <p className="text-[11px] text-[#737373] leading-snug flex gap-1.5">
                        <ShieldAlert className="w-3 h-3 flex-shrink-0 mt-0.5 text-amber-400" />
                        <span><span className="text-[#e5e5e5] font-medium">Figures removed</span> — a number couldn't be matched to your data, so it was taken out before you saw it.</span>
                    </p>
                </div>
            )}
        </div>
    );
}

function MiniStat({ label, value, tone }: { label: string; value: string | number; tone?: "ok" | "warn" }) {
    const color = tone === "warn" ? "text-red-400" : tone === "ok" ? "text-emerald-400" : "text-[#e5e5e5]";
    return (
        <div className="rounded-lg bg-[#141414] border border-[#1a1a1a] p-3">
            <p className="text-xs text-[#525252] mb-1">{label}</p>
            <p className={`text-sm font-bold ${color}`}>{value}</p>
        </div>
    );
}
