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
import dynamic from "next/dynamic";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import {
    Brain, TrendingUp, AlertTriangle, CheckCircle,
    RefreshCw, Zap, Shield, Activity, ArrowRight,
} from "lucide-react";
import Link from "next/link";
import { formatKES } from "@/lib/format";
import EmptyState from "@/components/ui/EmptyState";

const HowItWorks = dynamic(() => import("@/components/ai/HowItWorks").then((mod) => mod.HowItWorks));
import { StrategyAgent } from "@/components/ai/StrategyAgent";
import { WhatIfSimulator } from "@/components/ai/WhatIfSimulator";
import { DigitalTwin } from "@/components/ai/DigitalTwin";
import { getErrorMessage } from "@/lib/errors";

// Every AI module section is code-split (matches the pre-existing HowItWorks
// pattern above) — these are 340-880 line components loaded eagerly before
// this split, none of which are needed until the dashboard actually has data.
const DecisionsSection = dynamic(() => import("./_components/DecisionsSection"));
const PricingSection = dynamic(() => import("./_components/PricingSection"));
const LaborSection = dynamic(() => import("./_components/LaborSection"));
const SupplyChainSection = dynamic(() => import("./_components/SupplyChainSection"));
const DataQualitySection = dynamic(() => import("./_components/DataQualitySection"));
const MenuEngineeringSection = dynamic(() => import("./_components/MenuEngineeringSection"));
const ProfitSection = dynamic(() => import("./_components/ProfitSection"));
const HealthBoostSection = dynamic(() => import("./_components/HealthBoostSection"));
const RevenueForecastSection = dynamic(() => import("./_components/RevenueForecastSection"));
const InventoryPredictionsSection = dynamic(() => import("./_components/InventoryPredictionsSection"));
const KdsSection = dynamic(() => import("./_components/KdsSection"));
const FraudSection = dynamic(() => import("./_components/FraudSection"));
const GraphImpactSection = dynamic(() => import("./_components/GraphImpactSection"));
const CashSection = dynamic(() => import("./_components/CashSection"));

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

export default function AiDashboard() {
    const { user } = useAuth();
    const [data, setData] = useState<DashboardData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

    const restaurantName = user?.restaurant_name || "Your Restaurant";

    const fetchData = async () => {
        setLoading(true);
        setError("");
        try {
            const res = await api.get("/ai/dashboard");
            setData(res.data);
            setLastUpdated(new Date());
        } catch (e) {
            setError(getErrorMessage(e, "Could not load AI data"));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchData(); }, []);

    if (loading) {
        return (
            <div className="space-y-4">
                <div className="bg-surface rounded-xl h-8 w-48 animate-pulse" />
                <div className="bg-surface rounded-xl h-40 animate-pulse" />
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                    {[...Array(4)].map((_, i) => (
                        <div key={i} className="bg-surface rounded-xl h-20 animate-pulse" />
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
        return (
            <div className="space-y-6">
                <EmptyState
                    pageTitle="AI Command Center"
                    pageSubtitle={`${restaurantName} — Getting started`}
                    icon={Brain}
                    title="Your AI agents are ready"
                    description="Add menu items, record some orders, and your AI agents will start generating real insights — pricing recommendations, inventory alerts, revenue forecasts."
                    actions={
                        <>
                            <Link
                                href="/dashboard/menu"
                                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--accent)] text-bg font-semibold text-sm hover:bg-[var(--accent-hover)] transition-colors"
                            >
                                Add menu items <ArrowRight className="w-3.5 h-3.5" />
                            </Link>
                            <Link
                                href="/dashboard/pos"
                                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-surface border border-border text-text text-sm hover:bg-surface-hover transition-colors"
                            >
                                Record first order
                            </Link>
                        </>
                    }
                />
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {[
                        { icon: TrendingUp, label: "Pricing Intelligence", desc: "Surge pricing, margin alerts, delivery gap analysis" },
                        { icon: Shield, label: "Stock Monitoring", desc: "Predictive restock alerts before you run out" },
                        { icon: Activity, label: "Revenue Forecasting", desc: "7-day and 30-day predictions with confidence bands" },
                    ].map((agent) => (
                        <div key={agent.label} className="rounded-xl border border-surface-hover bg-[#0f0f0f] p-5">
                            <agent.icon className="w-5 h-5 text-[var(--accent)] mb-3" />
                            <p className="text-text font-medium text-sm">{agent.label}</p>
                            <p className="text-text-dim text-xs mt-1">{agent.desc}</p>
                        </div>
                    ))}
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[50vh] space-y-4">
                <AlertTriangle className="w-10 h-10 text-amber-400" />
                <p className="text-text font-medium">Could not load AI data</p>
                <p className="text-text-dim text-sm text-center max-w-sm">{error}</p>
                <button
                    onClick={fetchData}
                    className="px-4 py-2 bg-[var(--accent)] text-bg font-semibold rounded-lg text-sm hover:bg-[var(--accent-hover)]"
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
                    <h1 className="text-2xl font-bold text-text">AI Command Center</h1>
                    <p className="text-text-dim mt-1 text-sm">
                        {restaurantName} — Real-time intelligence
                    </p>
                </div>
                <button
                    onClick={fetchData}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg bg-surface border border-border text-text-muted hover:text-text text-sm transition-colors"
                >
                    <RefreshCw className="w-3.5 h-3.5" />
                    <span>{lastUpdated ? lastUpdated.toLocaleTimeString() : "Refresh"}</span>
                </button>
            </div>

            {/* Health Score */}
            <div className={`rounded-xl border p-6 ${healthBg(hs)}`}>
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                        <p className="text-text-dim text-xs uppercase tracking-widest mb-1">System Health</p>
                        <p className={`text-4xl sm:text-6xl font-black ${healthColor(hs)}`}>{hs}</p>
                        <p className="text-text-dim text-xs mt-2">
                            WoW Revenue:{" "}
                            <span className={wowGrowth >= 0 ? "text-emerald-400" : "text-red-400"}>
                                {wowGrowth >= 0 ? "+" : ""}
                                {wowGrowth}%
                            </span>
                        </p>
                        <HowItWorks id="health" />
                    </div>
                    <div className="space-y-2 w-full sm:w-auto sm:min-w-[180px]">
                        {data!.health_breakdown.map((b, i) => (
                            <div key={i}>
                                <div className="flex justify-between text-xs text-text-dim mb-1">
                                    <span>{b.category}</span>
                                    <span>{b.score}</span>
                                </div>
                                <div className="w-full bg-surface-hover rounded-full h-1.5">
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
                    <div key={stat.label} className="rounded-xl border border-surface-hover bg-[#0f0f0f] p-4">
                        <p className="text-xs text-text-dim mb-1">{stat.label}</p>
                        <p className="text-xl font-bold text-text">{stat.value}</p>
                    </div>
                ))}
            </div>

            {/* CEO Strategy Agent — goal in, one prioritized plan out. */}
            <StrategyAgent />

            {/* Decision Intelligence — every agent's recommendations, ranked into
                one prioritised stream. The owner's "what should I do first" view. */}
            <DecisionsSection />

            {/* What-If Simulator — test a price change before committing. */}
            <WhatIfSimulator />

            {/* Digital Twin — forward revenue projection with calendar signals. */}
            <DigitalTwin />

            {/* Revenue Forecast — the 7-day statistical forecast with confidence
                bands. Distinct from the Digital Twin above: the twin projects a
                chosen horizon with demand movers; this is the straight
                sales-pattern forecast. Both surfaces existed only as raw API
                endpoints consumed by other pages (Orders, Stock) before. */}
            <RevenueForecastSection />

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
            <KdsSection />
            <LaborSection />
            <SupplyChainSection />
            <InventoryPredictionsSection />
            <GraphImpactSection />
            <CashSection />
            <FraudSection />
            <DataQualitySection />

            {/* Risks + Opportunities */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Risks */}
                <div className="rounded-xl border border-surface-hover bg-[#0f0f0f] p-5">
                    <h2 className="text-sm font-semibold text-text mb-4 flex items-center gap-2">
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
                                <div key={i} className={`p-3 rounded-lg border text-sm ${severityStyle[r.severity] || "border-border text-text-muted"}`}>
                                    <p className="font-medium">{r.risk}</p>
                                    <p className="text-xs opacity-70 mt-0.5">{r.detail}</p>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Opportunities */}
                <div className="rounded-xl border border-surface-hover bg-[#0f0f0f] p-5">
                    <h2 className="text-sm font-semibold text-text mb-4 flex items-center gap-2">
                        <TrendingUp className="w-4 h-4 text-emerald-400" />
                        Opportunities
                    </h2>
                    {data!.opportunities.length === 0 ? (
                        <p className="text-text-dim text-sm py-2">No opportunities flagged yet — keep adding data</p>
                    ) : (
                        <div className="space-y-2">
                            {data!.opportunities.map((o, i) => (
                                <div key={i} className="p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
                                    <p className="text-sm font-medium text-text">{o.opportunity}</p>
                                    <p className="text-emerald-400 text-xs font-medium mt-0.5">{o.potential}</p>
                                    <p className="text-text-dim text-xs">{o.detail}</p>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* Recent AI Actions */}
            <div className="rounded-xl border border-surface-hover bg-[#0f0f0f] p-5">
                <h2 className="text-sm font-semibold text-text mb-4 flex items-center gap-2">
                    <Zap className="w-4 h-4 text-[var(--accent)]" />
                    Recent AI Actions
                </h2>
                {data!.recent_ai_actions.length === 0 ? (
                    <p className="text-text-dim text-sm">No AI actions logged yet</p>
                ) : (
                    <div className="space-y-2">
                        {data!.recent_ai_actions.map((log, i) => (
                            <div key={i} className="flex justify-between items-center py-2 border-b border-surface-hover last:border-0">
                                <div>
                                    <p className="text-sm text-text">{log.action}</p>
                                    <p className="text-xs text-text-dim">{log.agent}</p>
                                </div>
                                <span className="text-xs text-text-dim bg-surface px-2 py-1 rounded-md whitespace-nowrap">{log.time}</span>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
