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

interface DashboardData {
    health_score: number;
    health_breakdown: { category: string; score: number; weight: number; detail: string }[];
    quick_stats: {
        today_orders: number;
        revenue_today_kes: string;
        total_revenue_30d_kes: string;
        avg_daily_revenue_kes: string;
        pending_orders: number;
        active_alerts: number;
        week_over_week_growth: number;
    };
    risks: { severity: string; risk: string; detail: string }[];
    opportunities: { opportunity: string; potential: string; agent: string }[];
    recent_ai_actions: { action: string; agent: string; time: string }[];
    restaurant: { name: string };
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

    // No data or genuinely empty restaurant → helpful onboarding empty state
    const isNewRestaurant = !data || data.quick_stats.today_orders === 0 && data.risks.length === 0;
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

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-start justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-[#e5e5e5]">AI Command Center</h1>
                    <p className="text-[#525252] mt-1 text-sm">
                        {data!.restaurant.name} — Real-time intelligence
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
                            <span className={qs.week_over_week_growth >= 0 ? "text-emerald-400" : "text-red-400"}>
                                {qs.week_over_week_growth >= 0 ? "+" : ""}
                                {qs.week_over_week_growth}%
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
                    { label: "Today's Revenue", value: qs.revenue_today_kes },
                    { label: "Orders Today", value: String(qs.today_orders) },
                    { label: "Active Alerts", value: String(qs.active_alerts) },
                    { label: "30-Day Revenue", value: qs.total_revenue_30d_kes },
                ].map((stat) => (
                    <div key={stat.label} className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-4">
                        <p className="text-xs text-[#525252] mb-1">{stat.label}</p>
                        <p className="text-xl font-bold text-[#e5e5e5]">{stat.value}</p>
                    </div>
                ))}
            </div>

            {/* AI pages links */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {[
                    { href: "/dashboard/ai/pricing", label: "Pricing Intelligence", icon: TrendingUp, desc: "Surge, reprice, stimulate" },
                    { href: "/dashboard/ai/labor",   label: "Labor Optimization",   icon: Activity,   desc: "Staffing & cost analysis" },
                    { href: "/dashboard/ai/menu",    label: "Menu Engineering",      icon: Brain,      desc: "Stars, dogs, margin leaks" },
                ].map((link) => (
                    <Link
                        key={link.href}
                        href={link.href}
                        className="flex items-center gap-3 rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-4 hover:border-[#d4a853]/40 hover:bg-[#141414] transition-colors group"
                    >
                        <link.icon className="w-5 h-5 text-[#d4a853]" />
                        <div>
                            <p className="text-sm font-medium text-[#e5e5e5]">{link.label}</p>
                            <p className="text-xs text-[#525252]">{link.desc}</p>
                        </div>
                        <ArrowRight className="w-4 h-4 text-[#525252] ml-auto group-hover:text-[#d4a853] transition-colors" />
                    </Link>
                ))}
            </div>

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
                                    <p className="text-[#525252] text-xs">{o.agent}</p>
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
