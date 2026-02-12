"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { motion } from "framer-motion";
import { Box, AlertTriangle, TrendingDown, TrendingUp, Minus, Zap, BarChart3 } from "lucide-react";

export default function InventoryIntelPage() {
    const [data, setData] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [view, setView] = useState<"heatmap" | "items" | "alerts">("heatmap");

    useEffect(() => {
        api.get("/ai/inventory-predictions").then(r => { setData(r.data); setLoading(false); }).catch(() => setLoading(false));
    }, []);

    if (loading) return <div className="space-y-4 animate-pulse">{[...Array(3)].map((_, i) => <div key={i} className="glass rounded-xl h-24" />)}</div>;
    if (!data) return <p className="text-gray-500">Failed to load inventory data.</p>;

    const { summary, items, heatmap, alerts } = data;
    const s = summary || {};

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="glass rounded-2xl p-6 relative overflow-hidden">
                <div className="absolute top-0 right-0 w-64 h-64 bg-cyan-600/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
                <div className="relative">
                    <div className="flex items-center gap-2 mb-2">
                        <Box className="w-5 h-5 text-cyan-400" />
                        <span className="text-sm text-cyan-400 font-medium">Inventory Intelligence</span>
                    </div>
                    <h1 className="text-2xl font-bold mb-4">Stock Health & Predictions</h1>
                    <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
                        <MiniStat label="Items" value={s.total_items} />
                        <MiniStat label="Value" value={`KES ${(s.total_inventory_value || 0).toLocaleString()}`} color="text-emerald-400" />
                        <MiniStat label="Monthly Spend" value={`KES ${(s.total_monthly_spend || 0).toLocaleString()}`} />
                        <MiniStat label="Critical" value={s.critical_items || 0} color={s.critical_items > 0 ? "text-red-400" : "text-emerald-400"} />
                        <MiniStat label="Low Stock" value={s.low_stock_items || 0} color={s.low_stock_items > 0 ? "text-amber-400" : "text-emerald-400"} />
                        <MiniStat label="Reorder" value={s.reorder_items || 0} color="text-cyan-400" />
                    </div>
                    {/* ABC Summary */}
                    <div className="flex items-center gap-4 mt-3">
                        <span className="text-xs text-gray-400">ABC Classification:</span>
                        {Object.entries(s.abc_breakdown || {}).map(([cls, count]) => (
                            <span key={cls} className={`px-2 py-0.5 rounded text-[10px] font-bold ${cls === "A" ? "bg-emerald-600/30 text-emerald-400" : cls === "B" ? "bg-cyan-600/30 text-cyan-400" : "bg-gray-600/30 text-gray-400"}`}>
                                {cls}: {count as number}
                            </span>
                        ))}
                    </div>
                </div>
            </div>

            {/* Tabs */}
            <div className="flex gap-2">
                {(["heatmap", "items", "alerts"] as const).map(t => (
                    <button key={t} onClick={() => setView(t)}
                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${view === t ? "bg-indigo-600 text-white" : "glass text-gray-400 hover:text-white"}`}>
                        {t === "heatmap" ? "Health Heatmap" : t === "items" ? "Item Detail" : `Alerts (${(alerts || []).length})`}
                    </button>
                ))}
            </div>

            {/* Heatmap View */}
            {view === "heatmap" && (
                <div className="glass rounded-2xl p-6">
                    <h3 className="font-semibold mb-4 flex items-center gap-2"><BarChart3 className="w-4 h-4 text-cyan-400" />Stock Health Scores</h3>
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
                        {(heatmap || []).map((h: any, i: number) => (
                            <motion.div key={h.name} initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.04 }}
                                className={`p-4 rounded-xl border ${healthBorder(h.health)} relative group cursor-pointer hover:ring-1 hover:ring-indigo-400 transition-all`}>
                                <div className="flex items-center justify-between mb-2">
                                    <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${h.abc_class === "A" ? "bg-emerald-600/30 text-emerald-400" : h.abc_class === "B" ? "bg-cyan-600/30 text-cyan-400" : "bg-gray-600/30 text-gray-400"}`}>{h.abc_class}</span>
                                    <StatusDot status={h.status} />
                                </div>
                                <p className="text-sm font-medium truncate">{h.name}</p>
                                <p className={`text-2xl font-bold mt-1 ${healthColor(h.health)}`}>{h.health}</p>
                                <p className="text-[10px] text-gray-500">{h.status}</p>
                                {/* Tooltip */}
                                <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block bg-gray-800 border border-gray-700 rounded-lg p-3 text-xs whitespace-nowrap z-10">
                                    <p className="font-medium mb-1">{h.name}</p>
                                    <p>Stock: {h.current_qty} {h.unit}</p>
                                    <p>Daily Usage: {h.daily_usage}/day</p>
                                    <p>Days Left: {h.days_until_depletion}</p>
                                    <p>Waste: {h.waste_pct}%</p>
                                </div>
                            </motion.div>
                        ))}
                    </div>
                </div>
            )}

            {/* Items Detail View */}
            {view === "items" && (
                <div className="glass rounded-2xl overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-gray-700/50">
                                    <th className="text-left p-4 text-gray-400 font-medium">Item</th>
                                    <th className="text-center p-4 text-gray-400 font-medium">ABC</th>
                                    <th className="text-right p-4 text-gray-400 font-medium">Stock</th>
                                    <th className="text-right p-4 text-gray-400 font-medium">Daily Use</th>
                                    <th className="text-right p-4 text-gray-400 font-medium">Days Left</th>
                                    <th className="text-right p-4 text-gray-400 font-medium">EOQ</th>
                                    <th className="text-right p-4 text-gray-400 font-medium">Reorder At</th>
                                    <th className="text-right p-4 text-gray-400 font-medium">Waste %</th>
                                    <th className="text-center p-4 text-gray-400 font-medium">Trend</th>
                                    <th className="text-center p-4 text-gray-400 font-medium">Spoilage</th>
                                </tr>
                            </thead>
                            <tbody>
                                {(items || []).map((item: any, i: number) => (
                                    <motion.tr key={item.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.04 }}
                                        className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                                        <td className="p-4 font-medium">{item.name}</td>
                                        <td className="p-4 text-center"><ABCBadge cls={item.abc_class} /></td>
                                        <td className="p-4 text-right">{item.current_qty} {item.unit}</td>
                                        <td className="p-4 text-right">{item.avg_daily_usage}</td>
                                        <td className="p-4 text-right"><DaysLeftBadge days={item.days_until_depletion} /></td>
                                        <td className="p-4 text-right">{item.eoq}</td>
                                        <td className="p-4 text-right">{item.reorder_point}</td>
                                        <td className="p-4 text-right"><WasteBadge pct={item.waste_pct} /></td>
                                        <td className="p-4 text-center"><TrendIcon trend={item.consumption_trend} /></td>
                                        <td className="p-4 text-center">
                                            {item.spoilage_risk_score > 50 ? (
                                                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-red-600/30 text-red-400">{item.spoilage_risk_score}%</span>
                                            ) : (
                                                <span className="text-xs text-gray-500">{item.spoilage_risk_score}%</span>
                                            )}
                                        </td>
                                    </motion.tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* Alerts View */}
            {view === "alerts" && (
                <div className="space-y-3">
                    {(alerts || []).length === 0 ? (
                        <div className="glass rounded-xl p-6 text-center">
                            <p className="text-gray-500">No inventory alerts at this time. All items healthy.</p>
                        </div>
                    ) : (
                        (alerts || []).map((a: any, i: number) => (
                            <motion.div key={i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}
                                className="glass rounded-xl p-4 flex items-start gap-3">
                                <span className={`mt-0.5 px-2 py-0.5 rounded text-[10px] font-bold uppercase ${a.severity === "critical" ? "bg-red-600/30 text-red-400" : a.severity === "high" ? "bg-orange-600/30 text-orange-400" : "bg-amber-600/30 text-amber-400"}`}>{a.severity}</span>
                                <div className="flex-1">
                                    <p className="text-sm font-medium">{a.item}</p>
                                    <p className="text-xs text-gray-400 mt-0.5">{a.message}</p>
                                    <p className="text-xs text-indigo-400 mt-1">{a.action}</p>
                                </div>
                            </motion.div>
                        ))
                    )}
                </div>
            )}
        </div>
    );
}

/* ─── Subcomponents ─── */
function MiniStat({ label, value, color }: { label: string; value: any; color?: string }) {
    return (
        <div className="p-3 rounded-lg bg-gray-800/40 border border-gray-700/50">
            <p className="text-xs text-gray-400">{label}</p>
            <p className={`text-lg font-bold ${color || "text-white"}`}>{value}</p>
        </div>
    );
}

function ABCBadge({ cls }: { cls: string }) {
    const m: Record<string, string> = { A: "bg-emerald-600/30 text-emerald-400", B: "bg-cyan-600/30 text-cyan-400", C: "bg-gray-600/30 text-gray-400" };
    return <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${m[cls] || ""}`}>{cls}</span>;
}

function DaysLeftBadge({ days }: { days: number }) {
    if (days <= 3) return <span className="text-red-400 font-bold">{days}d</span>;
    if (days <= 7) return <span className="text-amber-400">{days}d</span>;
    return <span className="text-gray-300">{days}d</span>;
}

function WasteBadge({ pct }: { pct: number }) {
    if (pct > 10) return <span className="text-red-400 font-bold">{pct}%</span>;
    if (pct > 5) return <span className="text-amber-400">{pct}%</span>;
    return <span className="text-gray-400">{pct}%</span>;
}

function TrendIcon({ trend }: { trend: string }) {
    if (trend === "increasing") return <TrendingUp className="w-4 h-4 text-red-400 mx-auto" />;
    if (trend === "decreasing") return <TrendingDown className="w-4 h-4 text-emerald-400 mx-auto" />;
    return <Minus className="w-4 h-4 text-gray-500 mx-auto" />;
}

function StatusDot({ status }: { status: string }) {
    const c = status === "critical" ? "bg-red-400" : status === "low" ? "bg-amber-400" : status === "reorder" ? "bg-cyan-400" : "bg-emerald-400";
    return <span className={`w-2 h-2 rounded-full ${c}`} />;
}

function healthColor(h: number) { return h >= 80 ? "text-emerald-400" : h >= 60 ? "text-amber-400" : "text-red-400"; }
function healthBorder(h: number) { return h >= 80 ? "border-emerald-500/20 bg-emerald-900/10" : h >= 60 ? "border-amber-500/20 bg-amber-900/10" : "border-red-500/20 bg-red-900/10"; }
