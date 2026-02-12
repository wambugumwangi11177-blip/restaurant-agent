"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { motion } from "framer-motion";
import { CalendarRange, AlertTriangle, Users, Clock, DollarSign, TrendingUp, Lightbulb, BarChart3 } from "lucide-react";

export default function ReservationsPage() {
    const [data, setData] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get("/ai/reservation-insights").then(r => { setData(r.data); setLoading(false); }).catch(() => setLoading(false));
    }, []);

    if (loading) return <div className="space-y-4 animate-pulse">{[...Array(3)].map((_, i) => <div key={i} className="glass rounded-xl h-24" />)}</div>;
    if (!data) return <p className="text-gray-500">Failed to load reservation data.</p>;

    const { no_show_analysis, revenue_impact, table_utilization, lead_time_analysis, overbooking, peak_windows, party_size, recommendations, revpash } = data;
    const ns = no_show_analysis || {};
    const dep = ns.deposit_analysis || {};
    const ri = revenue_impact || {};
    const lt = lead_time_analysis || {};
    const ob = overbooking || {};
    const rv = revpash || {};

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="glass rounded-2xl p-6 relative overflow-hidden">
                <div className="absolute top-0 right-0 w-64 h-64 bg-amber-600/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
                <div className="relative">
                    <div className="flex items-center gap-2 mb-2">
                        <CalendarRange className="w-5 h-5 text-amber-400" />
                        <span className="text-sm text-amber-400 font-medium">Reservation Intelligence</span>
                    </div>
                    <h1 className="text-2xl font-bold mb-4">Reservations & No-Show Analytics</h1>
                    <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
                        <QS label="Total Reservations" value={ns.total_reservations} />
                        <QS label="No-Show Rate" value={`${ns.no_show_rate}%`} color={ns.no_show_rate > 15 ? "text-red-400" : "text-amber-400"} />
                        <QS label="Completion Rate" value={`${ns.completion_rate}%`} color="text-emerald-400" />
                        <QS label="RevPASH" value={`KES ${rv.revpash?.toLocaleString() || 0}`} color="text-cyan-400" />
                        <QS label="Rev Lost (No-Shows)" value={formatKES(ri.estimated_revenue_lost)} color="text-red-400" />
                    </div>
                </div>
            </div>

            {/* Two-column: No-Show Analysis + Deposit Impact */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* No-Show Breakdown */}
                <div className="glass rounded-2xl p-6">
                    <h3 className="font-semibold mb-4 flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-red-400" />No-Show by Day</h3>
                    <div className="space-y-2">
                        {(ns.by_day || []).map((d: any) => {
                            const maxR = Math.max(...(ns.by_day || []).map((x: any) => x.no_show_rate || 0));
                            const pct = maxR > 0 ? (d.no_show_rate / maxR) * 100 : 0;
                            return (
                                <div key={d.day} className="flex items-center gap-3">
                                    <span className="w-12 text-xs text-gray-400">{d.day.slice(0, 3)}</span>
                                    <div className="flex-1 bg-gray-800 rounded-full h-3 overflow-hidden">
                                        <motion.div initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.5 }}
                                            className="h-full rounded-full bg-gradient-to-r from-red-500 to-amber-500" />
                                    </div>
                                    <span className="w-20 text-xs text-right">
                                        <span className={d.no_show_rate > 20 ? "text-red-400 font-bold" : "text-gray-300"}>{d.no_show_rate}%</span>
                                        <span className="text-gray-500 ml-1">({d.total})</span>
                                    </span>
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Deposit Impact */}
                <div className="glass rounded-2xl p-6">
                    <h3 className="font-semibold mb-4 flex items-center gap-2"><DollarSign className="w-4 h-4 text-emerald-400" />Deposit Effectiveness</h3>
                    {dep.with_deposit && (
                        <div className="space-y-4">
                            <div className="grid grid-cols-2 gap-4">
                                <div className="p-4 rounded-xl bg-emerald-900/10 border border-emerald-500/20 text-center">
                                    <p className="text-xs text-gray-400 mb-1">With Deposit</p>
                                    <p className="text-2xl font-bold text-emerald-400">{dep.with_deposit.no_show_rate}%</p>
                                    <p className="text-[10px] text-gray-500">{dep.with_deposit.count} bookings</p>
                                </div>
                                <div className="p-4 rounded-xl bg-red-900/10 border border-red-500/20 text-center">
                                    <p className="text-xs text-gray-400 mb-1">Without Deposit</p>
                                    <p className="text-2xl font-bold text-red-400">{dep.without_deposit?.no_show_rate}%</p>
                                    <p className="text-[10px] text-gray-500">{dep.without_deposit?.count} bookings</p>
                                </div>
                            </div>
                            <p className="text-sm text-center text-gray-400">
                                Deposits reduce no-shows by <span className="text-emerald-400 font-bold">{dep.deposit_effectiveness?.toFixed(1)}%</span>
                            </p>
                        </div>
                    )}

                    {/* Overbooking Recommendation */}
                    <div className="mt-6 p-4 rounded-xl bg-gray-800/30 border border-gray-700/50">
                        <div className="flex items-center justify-between mb-2">
                            <span className="text-sm font-medium">Overbooking Recommendation</span>
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${ob.risk_level === "high" ? "bg-red-600/30 text-red-400" : ob.risk_level === "medium" ? "bg-amber-600/30 text-amber-400" : "bg-emerald-600/30 text-emerald-400"}`}>{ob.risk_level} risk</span>
                        </div>
                        <p className="text-2xl font-bold text-indigo-400">{ob.recommended_rate}%</p>
                        <p className="text-xs text-gray-400 mt-1">Based on {ns.no_show_rate}% no-show rate with {ob.safety_margin} safety margin</p>
                    </div>
                </div>
            </div>

            {/* Peak Windows + Party Size */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Peak Demand Windows */}
                <div className="glass rounded-2xl p-6">
                    <h3 className="font-semibold mb-4 flex items-center gap-2"><Clock className="w-4 h-4 text-cyan-400" />Peak Demand Windows</h3>
                    <div className="space-y-2">
                        {(peak_windows || []).map((pw: any, i: number) => (
                            <motion.div key={i} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.1 }}
                                className="flex items-center justify-between p-3 rounded-lg bg-gray-800/30 border border-gray-700/50">
                                <div>
                                    <p className="text-sm font-medium">{pw.day} — {pw.slot}</p>
                                    <p className="text-xs text-gray-400">{pw.count} reservations</p>
                                </div>
                                <span className="text-sm text-cyan-400 font-medium">Avg party: {pw.avg_party_size}</span>
                            </motion.div>
                        ))}
                        {(!peak_windows || peak_windows.length === 0) && <p className="text-gray-500 text-sm">No peak windows identified yet.</p>}
                    </div>
                </div>

                {/* Party Size Distribution */}
                <div className="glass rounded-2xl p-6">
                    <h3 className="font-semibold mb-4 flex items-center gap-2"><Users className="w-4 h-4 text-indigo-400" />Party Size Distribution</h3>
                    <div className="space-y-2">
                        {(party_size || []).map((ps: any) => {
                            const maxC = Math.max(...(party_size || []).map((x: any) => x.count || 0));
                            const pct = maxC > 0 ? (ps.count / maxC) * 100 : 0;
                            return (
                                <div key={ps.size} className="flex items-center gap-3">
                                    <span className="w-16 text-xs text-gray-400">{ps.size} guests</span>
                                    <div className="flex-1 bg-gray-800 rounded-full h-3 overflow-hidden">
                                        <motion.div initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.5 }}
                                            className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-cyan-500" />
                                    </div>
                                    <span className="w-16 text-xs text-right text-gray-300">{ps.count} ({ps.share_pct}%)</span>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>

            {/* Table Utilization */}
            {table_utilization && (
                <div className="glass rounded-2xl p-6">
                    <h3 className="font-semibold mb-4 flex items-center gap-2"><BarChart3 className="w-4 h-4 text-emerald-400" />Table Utilization</h3>
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                        <Stat label="Total Capacity" value={`${table_utilization.total_seats} seats`} />
                        <Stat label="Avg Covers/Day" value={rv.avg_covers_per_day} />
                        <Stat label="Avg Turnover" value={`${table_utilization.avg_turnover_rate}x/day`} />
                        <Stat label="Utilization" value={`${table_utilization.utilization_pct}%`} color={table_utilization.utilization_pct >= 70 ? "text-emerald-400" : "text-amber-400"} />
                    </div>
                </div>
            )}

            {/* Recommendations */}
            <div className="glass rounded-2xl p-6">
                <h3 className="font-semibold mb-4 flex items-center gap-2"><Lightbulb className="w-4 h-4 text-amber-400" />AI Recommendations</h3>
                <div className="space-y-3">
                    {(recommendations || []).map((r: any, i: number) => (
                        <motion.div key={i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.1 }}
                            className="p-4 rounded-xl bg-gray-800/30 border border-gray-700/50">
                            <div className="flex items-start gap-3">
                                <span className={`mt-0.5 px-2 py-0.5 rounded text-[10px] font-bold uppercase ${r.priority === "high" ? "bg-red-600/30 text-red-400" : r.priority === "medium" ? "bg-amber-600/30 text-amber-400" : "bg-gray-600/30 text-gray-400"}`}>{r.priority}</span>
                                <div>
                                    <p className="text-sm font-medium">{r.message}</p>
                                    <p className="text-xs text-indigo-400 mt-1">{r.action}</p>
                                    <p className="text-xs text-gray-500 mt-0.5">{r.impact}</p>
                                </div>
                            </div>
                        </motion.div>
                    ))}
                </div>
            </div>
        </div>
    );
}

/* ─── Helpers ─── */
function QS({ label, value, color }: { label: string; value: any; color?: string }) {
    return (
        <div className="p-3 rounded-lg bg-gray-800/40 border border-gray-700/50">
            <p className="text-xs text-gray-400">{label}</p>
            <p className={`text-lg font-bold ${color || "text-white"}`}>{value}</p>
        </div>
    );
}

function Stat({ label, value, color }: { label: string; value: any; color?: string }) {
    return (
        <div className="p-4 rounded-xl bg-gray-800/30 border border-gray-700/50 text-center">
            <p className="text-xs text-gray-400 mb-1">{label}</p>
            <p className={`text-xl font-bold ${color || "text-white"}`}>{value}</p>
        </div>
    );
}

function formatKES(cents: number) {
    if (!cents) return "KES 0";
    return `KES ${(cents / 100).toLocaleString("en-KE", { maximumFractionDigits: 0 })}`;
}
