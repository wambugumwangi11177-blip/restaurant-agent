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
    RefreshCw, Zap, Shield, Activity, ArrowRight, Truck,
} from "lucide-react";
import Link from "next/link";
import { formatKES } from "@/lib/format";
import { useAiModule } from "@/lib/useAiModule";
import { HowItWorks } from "@/components/ai/HowItWorks";
import { NarrativeBlock, type Narrative } from "@/components/ai/NarrativeBlock";
import { ExplainButton } from "@/components/ai/ExplainButton";
import { MiniStat } from "@/components/ai/MiniStat";
import { ModuleShell } from "@/components/ai/ModuleShell";

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
            <SupplyChainSection />
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

/* ── Inline AI module sections ─────────────────────────────────────────── */

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

function SupplyChainSection() {
    interface Supplier {
        id: number; name: string; reliability_score: number; reliability_label: string;
        delivered_on_time: number; delivered_late: number; pending_orders: number;
        avg_lead_days: number; lead_time_variance: number; cost_trend_pct: number; cost_trend_label: string; at_risk: boolean;
    }
    interface SupplyData {
        summary: { total_suppliers: number; overdue_orders: number; at_risk_suppliers: number; avg_reliability_pct: number };
        suppliers: Supplier[];
        overdue_orders: { supplier_name?: string; expected_at?: string }[];
        recommendations: { type?: string; priority?: string; message: string }[];
    }
    const { data, loading, error, retry } = useAiModule<SupplyData>("/ai/supply-chain");

    return (
        <ModuleShell icon={Truck} title="Supplier Intelligence" explainKey="supply" loading={loading} error={error} onRetry={retry}
            subtitle="Which suppliers deliver on time, whose prices are creeping up, and which orders are overdue.">
            {data && (
                <>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                        <MiniStat label="Suppliers" value={data.summary.total_suppliers} />
                        <MiniStat label="Avg reliability" value={`${data.summary.avg_reliability_pct}%`} tone={data.summary.avg_reliability_pct >= 85 ? "ok" : "warn"} />
                        <MiniStat label="At risk" value={data.summary.at_risk_suppliers} tone={data.summary.at_risk_suppliers > 0 ? "warn" : "ok"} />
                        <MiniStat label="Overdue orders" value={data.summary.overdue_orders} tone={data.summary.overdue_orders > 0 ? "warn" : "ok"} />
                    </div>
                    {data.suppliers.length === 0 ? (
                        <p className="text-[#525252] text-sm">No suppliers set up yet — add suppliers and purchase orders and this fills in.</p>
                    ) : (
                        <div className="space-y-2">
                            {data.suppliers.slice(0, 6).map((s) => (
                                <div key={s.id} className="p-3 rounded-lg bg-[#141414] border border-[#1a1a1a] text-sm">
                                    <div className="flex items-center justify-between gap-2">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <p className="text-[#e5e5e5]">{s.name}</p>
                                            <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${s.reliability_label === "EXCELLENT" ? "bg-emerald-500/10 text-emerald-400" : s.reliability_label === "GOOD" ? "bg-[#3b82f6]/10 text-[#60a5fa]" : "bg-red-500/10 text-red-400"}`}>{s.reliability_label}</span>
                                        </div>
                                        <span className={`text-xs font-medium whitespace-nowrap ${s.reliability_score >= 85 ? "text-emerald-400" : "text-red-400"}`}>{s.reliability_score}% on time</span>
                                    </div>
                                    <p className="text-xs text-[#525252] mt-1">
                                        {s.delivered_on_time} on time · {s.delivered_late} late
                                        {s.pending_orders > 0 ? ` · ${s.pending_orders} pending` : ""}
                                        {" · "}avg lead {s.avg_lead_days}d
                                        {s.cost_trend_label !== "stable" ? ` · prices ${s.cost_trend_label} ${Math.abs(s.cost_trend_pct)}%` : ""}
                                    </p>
                                </div>
                            ))}
                        </div>
                    )}
                    {data.recommendations && data.recommendations.length > 0 && (
                        <div className="mt-3 space-y-2">
                            {data.recommendations.slice(0, 4).map((r, i) => (
                                <div key={i} className="p-3 rounded-lg bg-[#141414] border border-[#1a1a1a] text-sm">
                                    <p className="text-[#e5e5e5]">{r.message}</p>
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

