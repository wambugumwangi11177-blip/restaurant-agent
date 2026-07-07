"use client";

/**
 * /dashboard/ai — AI Command Center
 *
 * FIX: This page replaces BOTH the old /dashboard/insights (hardcoded Lavy demo)
 * and the disconnected /ai-dashboard (used raw fetch, different layout).
 *
 * Now it:
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

            {/* AI modules — inline, not separate pages. These used to link to
                /dashboard/ai/pricing, /dashboard/ai/labor, /dashboard/ai/menu,
                none of which exist (a 404 on every click) — found 2026-07-07
                from a user report. Each section fetches and renders itself
                independently, so one module erroring doesn't take down the
                others or force a page navigation to see what's wrong. */}
            <PricingSection />
            <LaborSection />
            <MenuEngineeringSection />

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

function ModuleShell({
    icon: Icon, title, loading, error, onRetry, children,
}: {
    icon: any; title: string; loading: boolean; error: string; onRetry: () => void; children: React.ReactNode;
}) {
    return (
        <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
            <h2 className="text-sm font-semibold text-[#e5e5e5] mb-4 flex items-center gap-2">
                <Icon className="w-4 h-4 text-[#d4a853]" />
                {title}
            </h2>
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
        recommendations: { item_id: number; item_name: string; type: string; current_price: number; suggested_price: number; monthly_impact_cents: number; reason: string }[];
    }
    const { data, loading, error, retry } = useAiModule<PricingData>("/ai/pricing");

    return (
        <ModuleShell icon={TrendingUp} title="Pricing Intelligence" loading={loading} error={error} onRetry={retry}>
            {data && (
                <>
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
                            {data.recommendations.slice(0, 5).map((r) => (
                                <div key={r.item_id} className="flex items-center justify-between py-2 border-b border-[#1a1a1a] last:border-0 text-sm">
                                    <div>
                                        <p className="text-[#e5e5e5]">{r.item_name}</p>
                                        <p className="text-xs text-[#525252]">{r.reason}</p>
                                    </div>
                                    <span className="text-emerald-400 text-xs font-medium whitespace-nowrap">+{formatKES(r.monthly_impact_cents)}/mo</span>
                                </div>
                            ))}
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
        <ModuleShell icon={Activity} title="Labor Optimization" loading={loading} error={error} onRetry={retry}>
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

function MenuEngineeringSection() {
    interface MenuData {
        summary: { total_items: number; stars: number; plowhorses: number; puzzles: number; dogs: number; avg_food_cost_pct: number };
        recommendations: { item: string; action: string; reason: string; priority: string; impact: string }[];
    }
    const { data, loading, error, retry } = useAiModule<MenuData>("/ai/menu-engineering");

    return (
        <ModuleShell icon={Brain} title="Menu Engineering" loading={loading} error={error} onRetry={retry}>
            {data && (
                <>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                        <MiniStat label="Stars" value={data.summary.stars} tone="ok" />
                        <MiniStat label="Plowhorses" value={data.summary.plowhorses} />
                        <MiniStat label="Puzzles" value={data.summary.puzzles} />
                        <MiniStat label="Dogs" value={data.summary.dogs} tone={data.summary.dogs > 3 ? "warn" : undefined} />
                    </div>
                    {(!data.recommendations || data.recommendations.length === 0) ? (
                        <p className="text-[#525252] text-sm">{data.summary.total_items} menu items analysed — no urgent changes flagged.</p>
                    ) : (
                        <div className="space-y-2">
                            {data.recommendations.slice(0, 4).map((r, i) => (
                                <div key={i} className="p-3 rounded-lg bg-[#141414] border border-[#1a1a1a] text-sm">
                                    <p className="text-[#e5e5e5]">{r.item} — {r.action}</p>
                                    <p className="text-xs text-[#525252] mt-0.5">{r.reason}</p>
                                </div>
                            ))}
                        </div>
                    )}
                </>
            )}
        </ModuleShell>
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
