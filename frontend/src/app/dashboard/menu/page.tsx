"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { motion } from "framer-motion";
import { UtensilsCrossed, Star, TrendingUp, TrendingDown, Minus, ArrowUpRight, AlertTriangle, Lightbulb, BarChart3 } from "lucide-react";

export default function MenuEngineeringPage() {
    const [data, setData] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [view, setView] = useState<"matrix" | "recs" | "pareto">("matrix");

    useEffect(() => {
        api.get("/ai/menu-engineering").then(r => { setData(r.data); setLoading(false); }).catch(() => setLoading(false));
    }, []);

    if (loading) return <div className="space-y-4 animate-pulse">{[...Array(4)].map((_, i) => <div key={i} className="glass rounded-xl h-20" />)}</div>;
    if (!data) return <p className="text-gray-500">Failed to load menu data.</p>;

    const { matrix, summary, category_performance, pareto, recommendations, upsell_pairs } = data;
    const s = summary || {};

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="glass rounded-2xl p-6 relative overflow-hidden">
                <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-600/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
                <div className="relative">
                    <div className="flex items-center gap-2 mb-2">
                        <UtensilsCrossed className="w-5 h-5 text-indigo-400" />
                        <span className="text-sm text-indigo-400 font-medium">Menu Engineering AI</span>
                    </div>
                    <h1 className="text-2xl font-bold mb-4">Menu Performance Matrix</h1>

                    {/* Summary Stats */}
                    <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
                        <MiniStat label="Items" value={s.total_items} />
                        <MiniStat label="Stars" value={s.stars} color="text-yellow-400" icon="★" />
                        <MiniStat label="Plowhorses" value={s.plowhorses} color="text-blue-400" icon="🐴" />
                        <MiniStat label="Puzzles" value={s.puzzles} color="text-purple-400" icon="🧩" />
                        <MiniStat label="Dogs" value={s.dogs} color="text-red-400" icon="🐕" />
                        <MiniStat label="Menu Score" value={`${s.menu_optimization_score}/100`} color={s.menu_optimization_score >= 70 ? "text-emerald-400" : "text-amber-400"} />
                    </div>
                </div>
            </div>

            {/* Tab Navigation */}
            <div className="flex gap-2">
                {(["matrix", "recs", "pareto"] as const).map(t => (
                    <button key={t} onClick={() => setView(t)}
                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${view === t ? "bg-indigo-600 text-white" : "glass text-gray-400 hover:text-white"}`}>
                        {t === "matrix" ? "Item Matrix" : t === "recs" ? `Recommendations (${(recommendations || []).length})` : "Pareto Analysis"}
                    </button>
                ))}
            </div>

            {/* Matrix View */}
            {view === "matrix" && (
                <div className="glass rounded-2xl overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-gray-700/50">
                                    <th className="text-left p-4 text-gray-400 font-medium">Item</th>
                                    <th className="text-left p-4 text-gray-400 font-medium">Category</th>
                                    <th className="text-center p-4 text-gray-400 font-medium">Class</th>
                                    <th className="text-right p-4 text-gray-400 font-medium">Sold</th>
                                    <th className="text-right p-4 text-gray-400 font-medium">Revenue</th>
                                    <th className="text-right p-4 text-gray-400 font-medium">Margin %</th>
                                    <th className="text-right p-4 text-gray-400 font-medium">Food Cost %</th>
                                    <th className="text-center p-4 text-gray-400 font-medium">Trend</th>
                                    <th className="text-center p-4 text-gray-400 font-medium">Peak</th>
                                </tr>
                            </thead>
                            <tbody>
                                {(matrix || []).map((item: any, i: number) => (
                                    <motion.tr key={item.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.03 }}
                                        className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                                        <td className="p-4 font-medium">{item.name}</td>
                                        <td className="p-4 text-gray-400">{item.category}</td>
                                        <td className="p-4 text-center"><ClassBadge cls={item.classification} /></td>
                                        <td className="p-4 text-right">{item.qty_sold}</td>
                                        <td className="p-4 text-right text-emerald-400">{formatKES(item.revenue)}</td>
                                        <td className="p-4 text-right">{item.margin_pct}%</td>
                                        <td className="p-4 text-right"><CostBadge pct={item.food_cost_pct} /></td>
                                        <td className="p-4 text-center"><TrendIcon trend={item.trend} pct={item.trend_pct} /></td>
                                        <td className="p-4 text-center"><span className="text-xs text-gray-400">{item.peak_period}</span></td>
                                    </motion.tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* Recommendations View */}
            {view === "recs" && (
                <div className="space-y-3">
                    {(recommendations || []).map((r: any, i: number) => (
                        <motion.div key={i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}
                            className="glass rounded-xl p-4 flex items-start gap-3">
                            <span className={`mt-0.5 px-2 py-0.5 rounded text-[10px] font-bold uppercase ${r.priority === "high" ? "bg-red-600/30 text-red-400" : r.priority === "medium" ? "bg-amber-600/30 text-amber-400" : "bg-gray-600/30 text-gray-400"}`}>{r.priority}</span>
                            <div className="flex-1">
                                <p className="text-sm font-medium">{r.item}: <span className="text-indigo-400">{r.action}</span></p>
                                <p className="text-xs text-gray-400 mt-1">{r.reason}</p>
                                {r.impact && <p className="text-xs text-emerald-400 mt-1 flex items-center gap-1"><Lightbulb className="w-3 h-3" />{r.impact}</p>}
                            </div>
                        </motion.div>
                    ))}
                </div>
            )}

            {/* Pareto View */}
            {view === "pareto" && pareto && (
                <div className="glass rounded-2xl p-6">
                    <div className="flex items-center gap-2 mb-4">
                        <BarChart3 className="w-5 h-5 text-cyan-400" />
                        <h2 className="font-semibold">Revenue Concentration (80/20 Rule)</h2>
                    </div>
                    <p className="text-sm text-gray-400 mb-4">
                        <span className="text-white font-bold">{pareto.items_for_80_pct}</span> items ({pareto.concentration_ratio}% of menu) generate <span className="text-emerald-400 font-bold">80%</span> of total revenue.
                    </p>
                    <div className="space-y-2">
                        {(pareto.items || []).map((p: any) => (
                            <div key={p.rank} className="flex items-center gap-3">
                                <span className="w-6 text-xs text-gray-500 text-right">{p.rank}.</span>
                                <div className="flex-1 flex items-center gap-2">
                                    <span className="text-sm">{p.name}</span>
                                    <div className="flex-1 bg-gray-800 rounded-full h-2 overflow-hidden">
                                        <motion.div initial={{ width: 0 }} animate={{ width: `${p.cumulative_pct}%` }}
                                            transition={{ duration: 0.5, delay: p.rank * 0.05 }}
                                            className={`h-full rounded-full ${p.cumulative_pct <= 80 ? "bg-indigo-500" : "bg-gray-600"}`} />
                                    </div>
                                    <span className="text-xs text-gray-400 w-12 text-right">{p.cumulative_pct}%</span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Category Performance + Upsell Pairs */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="glass rounded-2xl p-6">
                    <h3 className="font-semibold mb-4">Category Performance</h3>
                    <div className="space-y-3">
                        {(category_performance || []).map((c: any) => (
                            <div key={c.category} className="flex items-center justify-between p-3 rounded-lg bg-gray-800/30">
                                <div>
                                    <p className="text-sm font-medium">{c.category}</p>
                                    <p className="text-xs text-gray-400">{c.item_count} items • {c.total_qty_sold} sold</p>
                                </div>
                                <div className="text-right">
                                    <p className="text-sm text-emerald-400 font-medium">{c.revenue_share_pct}% rev</p>
                                    <p className="text-xs text-gray-400">{c.avg_food_cost_pct}% cost</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                <div className="glass rounded-2xl p-6">
                    <h3 className="font-semibold mb-4">Upsell Pairs (Co-occurrence)</h3>
                    <div className="space-y-3">
                        {(upsell_pairs || []).map((u: any, i: number) => (
                            <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-gray-800/30">
                                <div className="flex items-center gap-2">
                                    <span className="text-sm">{u.item_a}</span>
                                    <span className="text-gray-500">+</span>
                                    <span className="text-sm">{u.item_b}</span>
                                </div>
                                <div className="text-right">
                                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${u.strength === "strong" ? "bg-emerald-600/30 text-emerald-400" : u.strength === "moderate" ? "bg-cyan-600/30 text-cyan-400" : "bg-gray-600/30 text-gray-400"}`}>{u.lift}x lift</span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}

/* ─── Subcomponents ─── */
function MiniStat({ label, value, color, icon }: { label: string; value: any; color?: string; icon?: string }) {
    return (
        <div className="p-3 rounded-lg bg-gray-800/40 border border-gray-700/50">
            <p className="text-xs text-gray-400">{label}</p>
            <p className={`text-lg font-bold ${color || "text-white"}`}>{icon ? `${icon} ${value}` : value}</p>
        </div>
    );
}

function ClassBadge({ cls }: { cls: string }) {
    const m: Record<string, string> = {
        Star: "bg-yellow-600/30 text-yellow-400", Plowhorse: "bg-blue-600/30 text-blue-400",
        Puzzle: "bg-purple-600/30 text-purple-400", Dog: "bg-red-600/30 text-red-400",
    };
    return <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${m[cls] || ""}`}>{cls}</span>;
}

function CostBadge({ pct }: { pct: number }) {
    const c = pct > 35 ? "text-red-400" : pct > 30 ? "text-amber-400" : "text-emerald-400";
    return <span className={c}>{pct}%</span>;
}

function TrendIcon({ trend, pct }: { trend: string; pct: number }) {
    if (trend === "rising") return <span className="text-emerald-400 flex items-center gap-0.5 justify-center text-xs"><TrendingUp className="w-3 h-3" />{pct > 0 ? `+${pct}%` : ""}</span>;
    if (trend === "falling") return <span className="text-red-400 flex items-center gap-0.5 justify-center text-xs"><TrendingDown className="w-3 h-3" />{pct}%</span>;
    return <span className="text-gray-500 flex items-center justify-center"><Minus className="w-3 h-3" /></span>;
}

function formatKES(cents: number) {
    if (!cents) return "KES 0";
    return `KES ${(cents / 100).toLocaleString("en-KE", { maximumFractionDigits: 0 })}`;
}
