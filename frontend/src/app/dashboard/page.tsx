"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { motion } from "framer-motion";
import {
    Brain, TrendingUp, TrendingDown, AlertTriangle, ShieldAlert,
    Zap, Package, UtensilsCrossed, CalendarRange, ChefHat,
    ArrowUpRight, ArrowDownRight, Activity,
} from "lucide-react";

interface HealthBreakdown {
    category: string; score: number; weight: number; detail: string;
}
interface Risk { risk: string; severity: string; detail: string; }
interface Opportunity { opportunity: string; potential: string; detail: string; }
interface Alert { source: string; item: string; message: string; severity: string; action: string; }

export default function DashboardPage() {
    const [data, setData] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get("/ai/dashboard").then(r => { setData(r.data); setLoading(false); }).catch(() => setLoading(false));
    }, []);

    if (loading) return <LoadingSkeleton />;
    if (!data) return <p className="text-gray-500">Failed to load dashboard data.</p>;

    const { health_score, health_breakdown, quick_stats, alerts, risks, opportunities } = data;
    const qs = quick_stats || {};

    return (
        <div className="space-y-6">
            {/* Hero: Health Score */}
            <div className="glass rounded-2xl p-8 relative overflow-hidden">
                <div className="absolute top-0 right-0 w-80 h-80 bg-indigo-600/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
                <div className="relative flex flex-col lg:flex-row lg:items-center gap-8">
                    <div className="flex-shrink-0">
                        <HealthRing score={health_score} />
                    </div>
                    <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                            <Brain className="w-5 h-5 text-indigo-400" />
                            <span className="text-sm text-indigo-400 font-medium">AI Operations Manager</span>
                        </div>
                        <h1 className="text-2xl font-bold mb-4">Restaurant Health Score</h1>
                        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
                            {(health_breakdown || []).map((b: HealthBreakdown) => (
                                <div key={b.category} className="p-3 rounded-lg bg-gray-800/40 border border-gray-700/50">
                                    <p className="text-xs text-gray-400 mb-1">{b.category}</p>
                                    <p className={`text-lg font-bold ${scoreColor(b.score)}`}>{b.score}/100</p>
                                    <p className="text-[10px] text-gray-500 mt-1 line-clamp-2">{b.detail}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            {/* Quick Stats */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <StatCard icon={TrendingUp} label="30-Day Revenue" value={formatKES(qs.total_revenue_30d)} color="emerald" />
                <StatCard icon={UtensilsCrossed} label="Today Orders" value={qs.today_orders || 0} color="indigo"
                    sub={qs.day_over_day_change ? `${qs.day_over_day_change > 0 ? '+' : ''}${qs.day_over_day_change}% vs yesterday` : undefined}
                    subUp={qs.day_over_day_change > 0}
                />
                <StatCard icon={Activity} label="Avg Order Value" value={formatKES(qs.avg_order_value)} color="cyan" />
                <StatCard icon={AlertTriangle} label="Active Alerts" value={qs.active_alerts || 0} color={qs.active_alerts > 5 ? "red" : "amber"} />
            </div>

            {/* Two-column: Risks + Opportunities */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Risks */}
                <div className="glass rounded-2xl p-6">
                    <div className="flex items-center gap-2 mb-4">
                        <ShieldAlert className="w-5 h-5 text-red-400" />
                        <h2 className="font-semibold">Risk Matrix</h2>
                    </div>
                    {(risks || []).length === 0 ? (
                        <p className="text-gray-500 text-sm">No active risks detected.</p>
                    ) : (
                        <div className="space-y-3">
                            {(risks as Risk[]).map((r, i) => (
                                <motion.div key={i} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.1 }}
                                    className="flex items-start gap-3 p-3 rounded-lg bg-gray-800/30 border border-gray-700/50">
                                    <span className={`mt-0.5 px-2 py-0.5 rounded text-[10px] font-bold uppercase ${severityBadge(r.severity)}`}>{r.severity}</span>
                                    <div>
                                        <p className="text-sm font-medium">{r.risk}</p>
                                        <p className="text-xs text-gray-400 mt-0.5">{r.detail}</p>
                                    </div>
                                </motion.div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Opportunities */}
                <div className="glass rounded-2xl p-6">
                    <div className="flex items-center gap-2 mb-4">
                        <Zap className="w-5 h-5 text-amber-400" />
                        <h2 className="font-semibold">Opportunity Radar</h2>
                    </div>
                    {(opportunities || []).length === 0 ? (
                        <p className="text-gray-500 text-sm">No opportunities identified yet.</p>
                    ) : (
                        <div className="space-y-3">
                            {(opportunities as Opportunity[]).map((o, i) => (
                                <motion.div key={i} initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.1 }}
                                    className="flex items-start gap-3 p-3 rounded-lg bg-gray-800/30 border border-gray-700/50">
                                    <span className={`mt-0.5 px-2 py-0.5 rounded text-[10px] font-bold uppercase ${potentialBadge(o.potential)}`}>{o.potential}</span>
                                    <div>
                                        <p className="text-sm font-medium">{o.opportunity}</p>
                                        <p className="text-xs text-gray-400 mt-0.5">{o.detail}</p>
                                    </div>
                                </motion.div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* Alerts Feed */}
            <div className="glass rounded-2xl p-6">
                <div className="flex items-center gap-2 mb-4">
                    <AlertTriangle className="w-5 h-5 text-amber-400" />
                    <h2 className="font-semibold">Cross-System Alerts</h2>
                    <span className="ml-auto text-xs text-gray-500">{(alerts || []).length} alerts</span>
                </div>
                <div className="space-y-2 max-h-80 overflow-y-auto pr-2">
                    {(alerts as Alert[] || []).map((a, i) => (
                        <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-gray-800/20 border border-gray-700/30">
                            <SourceIcon source={a.source} />
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-0.5">
                                    <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${severityBadge(a.severity)}`}>{a.severity}</span>
                                    <span className="text-[10px] text-gray-500 uppercase">{a.source}</span>
                                    {a.item && <span className="text-[10px] text-gray-400">• {a.item}</span>}
                                </div>
                                <p className="text-sm text-gray-300 truncate">{a.message}</p>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

/* ─── Components ─── */
function HealthRing({ score }: { score: number }) {
    const radius = 54;
    const circ = 2 * Math.PI * radius;
    const offset = circ - (score / 100) * circ;
    const color = score >= 80 ? "#10b981" : score >= 60 ? "#f59e0b" : "#ef4444";
    return (
        <div className="relative w-36 h-36">
            <svg className="w-full h-full -rotate-90" viewBox="0 0 120 120">
                <circle cx="60" cy="60" r={radius} fill="none" stroke="#1f2937" strokeWidth="8" />
                <motion.circle cx="60" cy="60" r={radius} fill="none" stroke={color} strokeWidth="8"
                    strokeLinecap="round" strokeDasharray={circ} initial={{ strokeDashoffset: circ }}
                    animate={{ strokeDashoffset: offset }} transition={{ duration: 1.2, ease: "easeOut" }} />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-3xl font-bold" style={{ color }}>{score}</span>
                <span className="text-[10px] text-gray-400">/ 100</span>
            </div>
        </div>
    );
}

function StatCard({ icon: Icon, label, value, color, sub, subUp }: {
    icon: any; label: string; value: any; color: string; sub?: string; subUp?: boolean;
}) {
    const bg: Record<string, string> = {
        emerald: "bg-emerald-600/20 border-emerald-500/30 text-emerald-400",
        indigo: "bg-indigo-600/20 border-indigo-500/30 text-indigo-400",
        cyan: "bg-cyan-600/20 border-cyan-500/30 text-cyan-400",
        amber: "bg-amber-600/20 border-amber-500/30 text-amber-400",
        red: "bg-red-600/20 border-red-500/30 text-red-400",
    };
    return (
        <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
                <div className={`w-9 h-9 rounded-lg border flex items-center justify-center ${bg[color]}`}><Icon className="w-4 h-4" /></div>
            </div>
            <p className="text-xl font-bold">{value}</p>
            <p className="text-xs text-gray-500 mt-0.5">{label}</p>
            {sub && <p className={`text-[10px] mt-1 flex items-center gap-0.5 ${subUp ? 'text-emerald-400' : 'text-red-400'}`}>
                {subUp ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}{sub}
            </p>}
        </motion.div>
    );
}

function SourceIcon({ source }: { source: string }) {
    const icons: Record<string, any> = { inventory: Package, kitchen: ChefHat, menu: UtensilsCrossed, reservations: CalendarRange };
    const Icon = icons[source] || AlertTriangle;
    return <Icon className="w-4 h-4 text-gray-500 mt-0.5 flex-shrink-0" />;
}

function LoadingSkeleton() {
    return (
        <div className="space-y-6 animate-pulse">
            <div className="glass rounded-2xl h-48" />
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">{[...Array(4)].map((_, i) => <div key={i} className="glass rounded-xl h-28" />)}</div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">{[...Array(2)].map((_, i) => <div key={i} className="glass rounded-2xl h-48" />)}</div>
        </div>
    );
}

/* ─── Helpers ─── */
function formatKES(cents: number) {
    if (!cents) return "KES 0";
    return `KES ${(cents / 100).toLocaleString("en-KE", { maximumFractionDigits: 0 })}`;
}
function scoreColor(s: number) { return s >= 80 ? "text-emerald-400" : s >= 60 ? "text-amber-400" : "text-red-400"; }
function severityBadge(s: string) {
    const m: Record<string, string> = { critical: "bg-red-600/30 text-red-400", high: "bg-orange-600/30 text-orange-400", warning: "bg-amber-600/30 text-amber-400", medium: "bg-yellow-600/30 text-yellow-400", info: "bg-blue-600/30 text-blue-400", low: "bg-gray-600/30 text-gray-400" };
    return m[s] || m.info;
}
function potentialBadge(p: string) {
    const m: Record<string, string> = { high: "bg-emerald-600/30 text-emerald-400", medium: "bg-cyan-600/30 text-cyan-400", low: "bg-gray-600/30 text-gray-400" };
    return m[p] || m.medium;
}
