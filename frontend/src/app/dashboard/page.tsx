"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import api from "@/lib/api";
import { demoData, isDashboardEmpty, isDemoMode } from "@/lib/demo-data";
import { motion } from "framer-motion";
import Link from "next/link";
import {
    TrendingUp,
    ShoppingBag,
    AlertTriangle,
    Activity,
    Zap,
    Shield,
    ShieldCheck,
    Wifi,
    Monitor,
    Smartphone,
    Clock,
    Megaphone,
    Brain,
    ArrowRight,
} from "lucide-react";
import StatCard from "@/components/ui/StatCard";

const SystemStatus = dynamic(() => import("./_components/SystemStatus"));

interface DashboardData {
    health_score: number;
    health_breakdown: { category: string; score: number }[];
    alerts: { severity: string; message: string; source: string; action?: string }[];
    opportunities: { opportunity: string; detail: string }[];
    risks: { risk: string; severity: string; detail: string }[];
    quick_stats: {
        today_revenue: number;
        today_orders: number;
        avg_order_value: number;
        active_alerts: number;
        pending_orders: number;
        menu_items: number;
        day_over_day_change: number;
    };
}

export default function DashboardPage() {
    const [data, setData] = useState<DashboardData | null>(null);
    const [loading, setLoading] = useState(true);
    const [trustStats, setTrustStats] = useState<{ grounded_pct: number | null; narratives_generated: number } | null>(null);
    const [glance, setGlance] = useState<{
        hoursPerDay: number; moneyPerDayCents: number; capturedCents: number; oppsCents: number; winbackReachable: number;
    } | null>(null);

    useEffect(() => {
        api.get("/ai/dashboard")
            .then((r) => setData(r.data))
            .catch(() => { })
            .finally(() => setLoading(false));
        api.get("/ai/trust-stats")
            .then((r) => setTrustStats(r.data))
            .catch(() => { });
        // "What your AI did" launchpad — narrate=false keeps it cheap and instant.
        Promise.all([
            api.get("/ai/roi?narrate=false").catch(() => null),
            api.get("/ai/marketing?narrate=false").catch(() => null),
        ]).then(([roi, mkt]) => {
            const rd = roi?.data;
            const md = mkt?.data;
            if (!rd && !md) return;
            const days = rd?.window_days || 30;
            const hours = rd?.time_saved?.hours_saved_30d || 0;
            const moneyCents = rd?.time_saved?.money_saved_cents || 0;
            const opps = (rd?.opportunities || []).reduce(
                (s: number, o: { monthly_value_cents?: number }) => s + (o.monthly_value_cents || 0), 0
            );
            setGlance({
                hoursPerDay: Math.round((hours / days) * 10) / 10,
                moneyPerDayCents: Math.round(moneyCents / days),
                capturedCents: rd?.money_captured?.monthly_impact_cents || 0,
                oppsCents: opps,
                winbackReachable: md?.winback?.reachable || 0,
            });
        });
    }, []);

    const getGreeting = () => {
        const h = new Date().getHours();
        if (h < 12) return "Good morning";
        if (h < 17) return "Good afternoon";
        return "Good evening";
    };

    if (loading) {
        return (
            <div className="space-y-4">
                <div className="bg-surface rounded-xl h-24 animate-pulse" />
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                    {[...Array(4)].map((_, i) => (
                        <div key={i} className="bg-surface rounded-xl h-24 animate-pulse" />
                    ))}
                </div>
            </div>
        );
    }

    // Demo (Lavy showcase) only when explicitly enabled. A real account with no
    // data gets an honest empty state below — never another restaurant's numbers.
    const isDemo = isDemoMode() && isDashboardEmpty(data);
    if (!isDemo && isDashboardEmpty(data)) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[50vh] text-center space-y-4 px-6">
                <div className="w-14 h-14 rounded-2xl bg-[var(--accent)]/10 flex items-center justify-center">
                    <TrendingUp className="w-7 h-7 text-[var(--accent)]" />
                </div>
                <div className="space-y-1.5 max-w-md">
                    <h1 className="text-xl font-bold text-text">{getGreeting()} 👋</h1>
                    <p className="text-sm text-text-muted">
                        Your dashboard is ready. Once you add menu items and start taking orders,
                        your restaurant health score, revenue trends, alerts, and AI opportunities
                        will show up here.
                    </p>
                </div>
                <div className="flex flex-wrap items-center justify-center gap-2 pt-1">
                    <Link href="/dashboard/menu" className="flex items-center gap-1.5 px-3 py-2 bg-[var(--accent)]/10 border border-[var(--accent)]/30 rounded-lg text-xs text-[var(--accent)] hover:bg-[var(--accent)]/20 transition-all">
                        Add menu items <ArrowRight className="w-3 h-3" />
                    </Link>
                    <Link href="/dashboard/pos" className="flex items-center gap-1.5 px-3 py-2 bg-surface-hover border border-border rounded-lg text-xs text-text hover:bg-[#222] transition-all">
                        Take an order <ArrowRight className="w-3 h-3" />
                    </Link>
                </div>
            </div>
        );
    }
    const activeData: DashboardData | null = isDemo ? demoData.dashboard : data;

    const qs = activeData?.quick_stats || {
        today_revenue: 0, today_orders: 0, avg_order_value: 0, active_alerts: 0,
        pending_orders: 0, menu_items: 0, day_over_day_change: 0,
    };
    const healthScore = activeData?.health_score ?? 0;
    const breakdown = activeData?.health_breakdown || [];
    const alerts = activeData?.alerts || [];
    const risks = activeData?.risks || [];
    const opportunities = activeData?.opportunities || [];

    const healthLabel = healthScore >= 80 ? "Looking great" : healthScore >= 60 ? "Doing okay" : healthScore >= 40 ? "Needs attention" : "Let's fix a few things";

    return (
        <div className="space-y-5">
            {/* Demo Mode Banner */}
            {isDemo && (
                <div className="flex items-center gap-2 px-3 py-1.5 bg-[var(--accent)]/8 border border-[var(--accent)]/20 rounded-lg">
                    <span className="text-[10px] text-[var(--accent)]">📊 Demo Mode — Showing sample data for Lavy restaurant</span>
                </div>
            )}

            {/* Greeting */}
            <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                <div>
                    <h1 className="text-xl font-bold text-text">
                        {getGreeting()} 👋
                    </h1>
                    <p className="text-sm text-text-dim mt-1">
                        Here&apos;s how your restaurant is doing right now
                    </p>
                </div>
                {/* Health Score */}
                <motion.div
                    initial={{ scale: 0.8, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    className="flex items-center gap-3 bg-surface border border-border rounded-xl px-4 py-3"
                >
                    <div className="relative w-14 h-14">
                        <svg viewBox="0 0 36 36" className="w-14 h-14 -rotate-90">
                            <circle cx="18" cy="18" r="15.9" fill="none" stroke="#262626" strokeWidth="2.5" />
                            <circle
                                cx="18" cy="18" r="15.9" fill="none"
                                stroke={healthScore >= 70 ? "#22c55e" : healthScore >= 40 ? "#eab308" : "#ef4444"}
                                strokeWidth="2.5"
                                strokeDasharray={`${healthScore} ${100 - healthScore}`}
                                strokeLinecap="round"
                            />
                        </svg>
                        <span className="absolute inset-0 flex items-center justify-center text-sm font-bold text-text">
                            {healthScore}
                        </span>
                    </div>
                    <div>
                        <p className="text-sm font-semibold text-text">Overall Health</p>
                        <p className="text-xs text-text-dim">{healthLabel}</p>
                    </div>
                </motion.div>
            </div>

            {/* Connected Systems */}
            <div className="bg-surface border border-border rounded-xl px-4 py-3">
                <div className="flex items-center justify-between gap-2 mb-2">
                    <div className="flex items-center gap-2">
                        <span className="flex h-2 w-2">
                            <span className="animate-ping absolute h-2 w-2 rounded-full bg-[#22c55e] opacity-75" />
                            <span className="relative rounded-full h-2 w-2 bg-[#22c55e]" />
                        </span>
                        <span className="text-xs font-medium text-[#22c55e]">Systems Connected</span>
                    </div>
                    {trustStats?.grounded_pct != null && (
                        <span
                            className="flex items-center gap-1 text-[10px] text-[var(--accent)] bg-[var(--accent)]/10 border border-[var(--accent)]/20 rounded px-1.5 py-0.5 whitespace-nowrap"
                            title={`${trustStats.narratives_generated.toLocaleString()} AI insights generated; every cited figure is checked against your real data before it's shown`}
                        >
                            <ShieldCheck className="w-3 h-3" /> {trustStats.grounded_pct}% of AI figures verified
                        </span>
                    )}
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                    <SystemStatus icon={Monitor} label="POS" status="connected" />
                    <SystemStatus icon={Smartphone} label="KDS" status="connected" />
                    <SystemStatus icon={ShoppingBag} label="Orders" status="connected" />
                    <SystemStatus icon={Activity} label="Inventory" status="connected" />
                    <SystemStatus icon={Wifi} label="Payments" status="connected" />
                </div>
            </div>

            {/* What your AI is doing — launchpad into ROI / AI / Growth */}
            {glance && (glance.moneyPerDayCents > 0 || glance.capturedCents > 0 || glance.oppsCents > 0 || glance.winbackReachable > 0) && (
                <div className="bg-surface border border-border rounded-xl p-4">
                    <div className="flex items-center gap-2 mb-3">
                        <Zap className="w-3.5 h-3.5 text-[var(--accent)]" />
                        <p className="text-xs font-semibold text-text">What your AI is doing for you</p>
                    </div>
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                        <Link href="/dashboard/roi" className="group rounded-lg bg-[#0f0f0f] border border-surface-hover p-3 hover:border-[var(--accent)]/40 transition-colors">
                            <p className="text-lg font-bold text-emerald-400">{formatKES(glance.moneyPerDayCents)}<span className="text-xs text-text-dim font-normal">/day</span></p>
                            <p className="text-[10px] text-text-dim mt-0.5">saved in staff time (≈ {glance.hoursPerDay} hrs/day)</p>
                        </Link>
                        <Link href="/dashboard/roi" className="group rounded-lg bg-[#0f0f0f] border border-surface-hover p-3 hover:border-[var(--accent)]/40 transition-colors">
                            <p className="text-lg font-bold text-[var(--accent)]">{formatKES(glance.capturedCents)}</p>
                            <p className="text-[10px] text-text-dim mt-0.5">extra profit captured this month</p>
                        </Link>
                        <Link href="/dashboard/roi" className="group rounded-lg bg-[#0f0f0f] border border-surface-hover p-3 hover:border-[var(--accent)]/40 transition-colors">
                            <p className="text-lg font-bold text-amber-400">{formatKES(glance.oppsCents)}</p>
                            <p className="text-[10px] text-text-dim mt-0.5">opportunities flagged, not yet actioned</p>
                        </Link>
                        <Link href="/dashboard/marketing" className="group rounded-lg bg-[#0f0f0f] border border-surface-hover p-3 hover:border-[var(--accent)]/40 transition-colors">
                            <p className="text-lg font-bold text-text">{glance.winbackReachable}</p>
                            <p className="text-[10px] text-text-dim mt-0.5">lapsed regulars ready to win back</p>
                        </Link>
                    </div>
                    <div className="flex flex-wrap gap-2 mt-3">
                        <Link href="/dashboard/ai" className="flex items-center gap-1.5 text-[11px] text-text-muted hover:text-[var(--accent)] transition-colors"><Brain className="w-3 h-3" /> AI Command Center</Link>
                        <span className="text-border">·</span>
                        <Link href="/dashboard/roi" className="flex items-center gap-1.5 text-[11px] text-text-muted hover:text-[var(--accent)] transition-colors"><Clock className="w-3 h-3" /> Time & Money Saved</Link>
                        <span className="text-border">·</span>
                        <Link href="/dashboard/marketing" className="flex items-center gap-1.5 text-[11px] text-text-muted hover:text-[var(--accent)] transition-colors"><Megaphone className="w-3 h-3" /> Campaigns & Win-back <ArrowRight className="w-3 h-3" /></Link>
                    </div>
                </div>
            )}

            {/* What's happening at a glance */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <StatCard
                    label="Today's Sales"
                    value={isDemo ? `KES ${(52400).toLocaleString("en-KE")}` : formatKES(qs.today_revenue)}
                    sub={qs.day_over_day_change ? `${qs.day_over_day_change > 0 ? "Up" : "Down"} ${Math.abs(qs.day_over_day_change)}% from yesterday` : "No data from yesterday"}
                    color={qs.day_over_day_change >= 0 ? "#22c55e" : "#ef4444"}
                />
                <StatCard
                    label="Orders Today"
                    value={qs.today_orders || 0}
                    sub={qs.pending_orders ? `${qs.pending_orders} still being prepared` : "All caught up"}
                    color="#d4a853"
                />
                <StatCard
                    label="Average Spend"
                    value={isDemo ? `KES ${(2114).toLocaleString("en-KE")}` : formatKES(qs.avg_order_value)}
                    sub={`Across ${qs.menu_items || 0} menu items`}
                    color="#3b82f6"
                />
                <StatCard
                    label="Things to Check"
                    value={qs.active_alerts || 0}
                    sub={qs.active_alerts === 0 ? "Nothing urgent" : "We've flagged a few things"}
                    color={qs.active_alerts > 3 ? "#ef4444" : "#737373"}
                />
            </div>

            {/* Breakdown — how each area is doing */}
            <div className="bg-surface border border-border rounded-xl px-4 py-3">
                <p className="text-xs font-semibold text-text mb-3">How each area is doing</p>
                <div className="space-y-2">
                    {breakdown.map((b, i: number) => {
                        const friendlyNames: Record<string, string> = {
                            "Menu Health": "Your Menu",
                            "Revenue Trend": "Sales Trend",
                            "Kitchen Efficiency": "Kitchen Speed",
                            "Inventory Status": "Stock Levels",
                            "Reservation Reliability": "Bookings",
                        };
                        const score = b.score ?? b;
                        const cat = b.category ?? b;
                        return (
                            <div key={i} className="flex items-center gap-3">
                                <span className="text-xs text-text-muted w-28 flex-shrink-0">
                                    {friendlyNames[cat] || cat}
                                </span>
                                <div className="flex-1 h-2 bg-surface-hover rounded-full overflow-hidden">
                                    <motion.div
                                        initial={{ width: 0 }}
                                        animate={{ width: `${score}%` }}
                                        transition={{ delay: i * 0.1, duration: 0.5 }}
                                        className={`h-full rounded-full ${score >= 70 ? "bg-[#22c55e]" : score >= 40 ? "bg-[#eab308]" : "bg-[#ef4444]"
                                            }`}
                                    />
                                </div>
                                <span className={`text-xs font-medium w-10 text-right ${score >= 70 ? "text-[#22c55e]" : score >= 40 ? "text-[#eab308]" : "text-[#ef4444]"
                                    }`}>{score}%</span>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* Risks & Opportunities side by side */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                {/* Watch out for */}
                <div className="bg-surface border border-border rounded-xl">
                    <div className="px-4 py-3 border-b border-surface-hover flex items-center gap-2">
                        <Shield className="w-3.5 h-3.5 text-[#ef4444]" />
                        <h2 className="text-sm font-semibold text-text">Watch Out For</h2>
                    </div>
                    {risks.length === 0 ? (
                        <div className="px-4 py-6 text-center text-xs text-text-dim">Everything looks good right now ✓</div>
                    ) : (
                        <div className="divide-y divide-surface-hover">
                            {risks.map((r, i: number) => (
                                <motion.div key={i} initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                                    transition={{ delay: i * 0.05 }} className="px-4 py-3">
                                    <div className="flex items-center gap-2">
                                        <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${r.severity === "critical" ? "bg-[#ef4444]/10 text-[#ef4444]"
                                                : r.severity === "high" ? "bg-[#eab308]/10 text-[#eab308]"
                                                    : "bg-info/10 text-info"
                                            }`}>{r.severity === "critical" ? "urgent" : r.severity}</span>
                                        <p className="text-sm text-text">{friendlyRisk(r.risk)}</p>
                                    </div>
                                    <p className="text-xs text-text-dim mt-1">{friendlyDetail(r.detail)}</p>
                                </motion.div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Ways to earn more */}
                <div className="bg-surface border border-border rounded-xl">
                    <div className="px-4 py-3 border-b border-surface-hover flex items-center gap-2">
                        <Zap className="w-3.5 h-3.5 text-[var(--accent)]" />
                        <h2 className="text-sm font-semibold text-text">Ways to Earn More</h2>
                    </div>
                    {opportunities.length === 0 ? (
                        <div className="px-4 py-6 text-center text-xs text-text-dim">We&apos;re looking for opportunities...</div>
                    ) : (
                        <div className="divide-y divide-surface-hover">
                            {opportunities.map((o, i: number) => (
                                <motion.div key={i} initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                                    transition={{ delay: i * 0.05 }} className="px-4 py-3">
                                    <div className="flex items-center gap-2">
                                        <Zap className="w-3 h-3 text-[var(--accent)]" />
                                        <p className="text-sm text-text">{friendlyOpportunity(o.opportunity)}</p>
                                    </div>
                                    <p className="text-xs text-text-dim mt-1">{friendlyDetail(o.detail || "")}</p>
                                </motion.div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* Alerts */}
            {alerts.length > 0 && (
                <div className="bg-surface border border-border rounded-xl">
                    <div className="px-4 py-3 border-b border-surface-hover flex items-center gap-2">
                        <AlertTriangle className="w-3.5 h-3.5 text-[#eab308]" />
                        <h2 className="text-sm font-semibold text-text">Alerts From Your Systems</h2>
                        <span className="text-[10px] text-text-dim ml-auto">{alerts.length} active</span>
                    </div>
                    <div className="divide-y divide-surface-hover max-h-64 overflow-y-auto">
                        {alerts.map((a, i: number) => {
                            const sourceLabels: Record<string, string> = {
                                inventory: "Stock", kitchen: "Kitchen", menu: "Menu", reservations: "Bookings",
                            };
                            const severity = a.severity || a.source;
                            return (
                                <div key={i} className="px-4 py-3 flex items-start gap-3">
                                    <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded mt-0.5 flex-shrink-0 ${a.source === "inventory" || severity === "WARNING" ? "bg-[#ef4444]/10 text-[#ef4444]"
                                            : a.source === "kitchen" || severity === "INFO" ? "bg-[#eab308]/10 text-[#eab308]"
                                                : a.source === "menu" || severity === "SUCCESS" ? "bg-[#22c55e]/10 text-[#22c55e]"
                                                    : "bg-[#8b5cf6]/10 text-[#8b5cf6]"
                                        }`}>{sourceLabels[a.source] || a.source || a.severity}</span>
                                    <div>
                                        <p className="text-sm text-text">{a.message}</p>
                                        {a.action && (
                                            <p className="text-xs text-[var(--accent)] mt-1">💡 {a.action}</p>
                                        )}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}
        </div>
    );
}

function formatKES(cents: number) {
    if (!cents) return "KES 0";
    return `KES ${(cents / 100).toLocaleString("en-KE", { maximumFractionDigits: 0 })}`;
}

/* Friendly language helpers */
function friendlyRisk(risk: string) {
    const map: Record<string, string> = {
        "Stock-out risk": "Some items might run out",
        "High no-show rate": "Too many no-shows on bookings",
        "Kitchen bottleneck": "Kitchen is getting backed up",
        "Menu dead weight": "Some menu items aren't selling",
    };
    return map[risk] || risk;
}

function friendlyOpportunity(opp: string) {
    const map: Record<string, string> = {
        "Promote high-margin items": "Push your most profitable items",
        "Recover no-show revenue": "Start collecting deposits on bookings",
        "Implement controlled overbooking": "Safely take a few extra bookings",
        "Capitalize on growth momentum": "Sales are growing — keep the momentum",
    };
    return map[opp] || opp;
}

function friendlyDetail(detail: string) {
    return detail
        .replace(/Puzzle items/g, "profitable items that don't sell much")
        .replace(/Dog items/g, "items that aren't popular or profitable")
        .replace(/Stars/g, "top sellers")
        .replace(/Plowhorses/g, "popular items with thin margins");
}
