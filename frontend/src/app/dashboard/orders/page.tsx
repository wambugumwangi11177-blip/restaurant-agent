"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { motion } from "framer-motion";
import { TrendingUp, TrendingDown, DollarSign, Clock, Calendar, AlertTriangle, BarChart3, Zap } from "lucide-react";

export default function RevenueOrdersPage() {
    const [data, setData] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get("/ai/revenue-forecast").then(r => { setData(r.data); setLoading(false); }).catch(() => setLoading(false));
    }, []);

    if (loading) return <div className="space-y-4 animate-pulse">{[...Array(4)].map((_, i) => <div key={i} className="glass rounded-xl h-24" />)}</div>;
    if (!data) return <p className="text-gray-500">Failed to load revenue data.</p>;

    const { trends, daily_revenue, hourly_pattern, weekly_pattern, revenue_by_type, revenue_by_category, check_analysis, anomalies, forecast } = data;
    const t = trends || {};

    return (
        <div className="space-y-6">
            {/* Header Stats */}
            <div className="glass rounded-2xl p-6 relative overflow-hidden">
                <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-600/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
                <div className="relative">
                    <div className="flex items-center gap-2 mb-2">
                        <TrendingUp className="w-5 h-5 text-emerald-400" />
                        <span className="text-sm text-emerald-400 font-medium">Revenue Intelligence</span>
                    </div>
                    <h1 className="text-2xl font-bold mb-4">Revenue & Order Analytics</h1>
                    <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
                        <QuickStat label="30-Day Revenue" value={formatKES(t.total_revenue)} />
                        <QuickStat label="Avg Daily" value={formatKES(t.avg_daily_revenue)} />
                        <QuickStat label="WoW Growth" value={`${t.week_over_week_growth > 0 ? "+" : ""}${t.week_over_week_growth}%`} color={t.week_over_week_growth >= 0 ? "text-emerald-400" : "text-red-400"} />
                        <QuickStat label="Avg Order" value={formatKES(t.avg_order_value)} />
                        <QuickStat label="Peak Day" value={t.peak_day} />
                    </div>
                </div>
            </div>

            {/* Revenue Time Series */}
            <div className="glass rounded-2xl p-6">
                <h2 className="font-semibold mb-4 flex items-center gap-2"><BarChart3 className="w-5 h-5 text-indigo-400" />Daily Revenue (30 Days)</h2>
                <div className="flex items-end gap-1 h-40">
                    {(daily_revenue || []).map((d: any, i: number) => {
                        const max = Math.max(...(daily_revenue || []).map((x: any) => x.revenue));
                        const pct = max > 0 ? (d.revenue / max) * 100 : 0;
                        return (
                            <motion.div key={d.date}
                                initial={{ height: 0 }} animate={{ height: `${pct}%` }} transition={{ delay: i * 0.02, duration: 0.3 }}
                                className="flex-1 bg-indigo-500/60 hover:bg-indigo-400/80 rounded-t transition-colors relative group cursor-pointer min-w-[4px]">
                                <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block bg-gray-800 border border-gray-700 rounded-lg p-2 text-xs whitespace-nowrap z-10">
                                    <p className="font-medium">{d.date}</p>
                                    <p className="text-emerald-400">{formatKES(d.revenue)}</p>
                                    <p className="text-gray-400">{d.orders} orders</p>
                                </div>
                            </motion.div>
                        );
                    })}
                </div>
                <div className="flex justify-between mt-2 text-[10px] text-gray-500">
                    <span>{daily_revenue?.[0]?.date}</span>
                    <span>{daily_revenue?.[daily_revenue.length - 1]?.date}</span>
                </div>
            </div>

            {/* Two-column: Weekly + By Type */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Weekly Pattern */}
                <div className="glass rounded-2xl p-6">
                    <h3 className="font-semibold mb-4 flex items-center gap-2"><Calendar className="w-4 h-4 text-cyan-400" />Weekly Pattern</h3>
                    <div className="space-y-2">
                        {(weekly_pattern || []).map((w: any) => {
                            const maxRev = Math.max(...(weekly_pattern || []).map((x: any) => x.avg_revenue));
                            const pct = maxRev > 0 ? (w.avg_revenue / maxRev) * 100 : 0;
                            return (
                                <div key={w.day} className="flex items-center gap-3">
                                    <span className="w-12 text-xs text-gray-400">{w.day.slice(0, 3)}</span>
                                    <div className="flex-1 bg-gray-800 rounded-full h-3 overflow-hidden">
                                        <motion.div initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.5 }}
                                            className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-cyan-500" />
                                    </div>
                                    <span className="text-xs text-gray-300 w-24 text-right">{formatKES(w.avg_revenue)}</span>
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Revenue by Order Type */}
                <div className="glass rounded-2xl p-6">
                    <h3 className="font-semibold mb-4 flex items-center gap-2"><DollarSign className="w-4 h-4 text-emerald-400" />Revenue by Order Type</h3>
                    <div className="space-y-3">
                        {(revenue_by_type || []).map((rt: any) => (
                            <div key={rt.type} className="p-3 rounded-lg bg-gray-800/30 border border-gray-700/50">
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-sm font-medium capitalize">{rt.type.replace("_", " ")}</span>
                                    <span className="text-sm text-emerald-400">{rt.share_pct}%</span>
                                </div>
                                <div className="bg-gray-800 rounded-full h-2 overflow-hidden">
                                    <motion.div initial={{ width: 0 }} animate={{ width: `${rt.share_pct}%` }}
                                        className="h-full rounded-full bg-emerald-500" />
                                </div>
                                <div className="flex justify-between mt-1 text-[10px] text-gray-500">
                                    <span>{rt.orders} orders</span>
                                    <span>Avg check: {formatKES(rt.avg_check)}</span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Hourly Heatmap */}
            <div className="glass rounded-2xl p-6">
                <h3 className="font-semibold mb-4 flex items-center gap-2"><Clock className="w-4 h-4 text-amber-400" />Hourly Revenue Heatmap</h3>
                <div className="grid grid-cols-12 lg:grid-cols-24 gap-1">
                    {(hourly_pattern || []).map((h: any) => {
                        const maxRev = Math.max(...(hourly_pattern || []).map((x: any) => x.avg_revenue));
                        const intensity = maxRev > 0 ? h.avg_revenue / maxRev : 0;
                        const bg = intensity > 0.7 ? "bg-indigo-500" : intensity > 0.4 ? "bg-indigo-600/70" : intensity > 0.1 ? "bg-indigo-800/50" : "bg-gray-800/30";
                        return (
                            <div key={h.hour} className={`${bg} rounded p-2 text-center relative group cursor-pointer transition-all hover:ring-1 hover:ring-indigo-400`}>
                                <span className="text-[9px] text-gray-400">{h.label.slice(0, 2)}</span>
                                {h.is_peak && <span className="absolute -top-1 -right-1 w-2 h-2 bg-amber-400 rounded-full" />}
                                <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block bg-gray-800 border border-gray-700 rounded-lg p-2 text-xs whitespace-nowrap z-10">
                                    <p className="font-medium">{h.label} ({h.period})</p>
                                    <p className="text-emerald-400">{formatKES(h.avg_revenue)} avg</p>
                                    <p className="text-gray-400">{h.avg_orders} orders/day</p>
                                </div>
                            </div>
                        );
                    })}
                </div>
                <p className="text-[10px] text-gray-500 mt-2">🟡 = peak hours</p>
            </div>

            {/* 7-Day Forecast + Anomalies */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="glass rounded-2xl p-6">
                    <h3 className="font-semibold mb-4 flex items-center gap-2"><Zap className="w-4 h-4 text-amber-400" />7-Day Revenue Forecast</h3>
                    <div className="space-y-2">
                        {(forecast || []).map((f: any) => (
                            <div key={f.date} className="flex items-center gap-3 p-2 rounded-lg bg-gray-800/20">
                                <span className="w-8 text-xs text-gray-400 font-medium">{f.day.slice(0, 3)}</span>
                                <div className="flex-1">
                                    <div className="flex items-center gap-1 text-sm">
                                        <span className="text-emerald-400 font-medium">{formatKES(f.predicted_revenue)}</span>
                                        <span className="text-[10px] text-gray-500">({formatKES(f.confidence_low)} - {formatKES(f.confidence_high)})</span>
                                    </div>
                                </div>
                                <span className="text-xs text-indigo-400">{f.confidence_pct}%</span>
                            </div>
                        ))}
                    </div>
                </div>

                <div className="glass rounded-2xl p-6">
                    <h3 className="font-semibold mb-4 flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-red-400" />Revenue Anomalies</h3>
                    {(anomalies || []).length === 0 ? (
                        <p className="text-gray-500 text-sm">No anomalies detected in the period.</p>
                    ) : (
                        <div className="space-y-3">
                            {(anomalies || []).map((a: any, i: number) => (
                                <div key={i} className="p-3 rounded-lg bg-gray-800/30 border border-gray-700/50">
                                    <div className="flex items-center justify-between mb-1">
                                        <span className="text-sm font-medium">{a.date}</span>
                                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${a.type === "spike" ? "bg-emerald-600/30 text-emerald-400" : "bg-red-600/30 text-red-400"}`}>{a.type}</span>
                                    </div>
                                    <p className="text-xs text-gray-400">Revenue: {formatKES(a.revenue)} ({a.deviation_pct > 0 ? "+" : ""}{a.deviation_pct}% vs expected {formatKES(a.expected)})</p>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

/* ─── Helpers ─── */
function QuickStat({ label, value, color }: { label: string; value: any; color?: string }) {
    return (
        <div className="p-3 rounded-lg bg-gray-800/40 border border-gray-700/50">
            <p className="text-xs text-gray-400">{label}</p>
            <p className={`text-lg font-bold ${color || "text-white"}`}>{value}</p>
        </div>
    );
}

function formatKES(cents: number) {
    if (!cents) return "KES 0";
    return `KES ${(cents / 100).toLocaleString("en-KE", { maximumFractionDigits: 0 })}`;
}
