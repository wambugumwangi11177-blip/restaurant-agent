"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { motion } from "framer-motion";
import { ShoppingBag, Clock, TrendingUp } from "lucide-react";

export default function OrdersPage() {
    const [orders, setOrders] = useState<any[]>([]);
    const [aiData, setAiData] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        Promise.all([
            api.get("/orders/").catch(() => ({ data: [] })),
            api.get("/ai/revenue-forecast").catch(() => ({ data: null })),
        ]).then(([ordersRes, aiRes]) => {
            setOrders(Array.isArray(ordersRes.data) ? ordersRes.data : []);
            setAiData(aiRes.data);
            setLoading(false);
        });
    }, []);

    if (loading) {
        return (
            <div className="space-y-3">
                {[...Array(5)].map((_, i) => (
                    <div key={i} className="bg-[#141414] rounded-xl h-16 animate-pulse" />
                ))}
            </div>
        );
    }

    const today = new Date().toISOString().split("T")[0];
    const todayOrders = orders.filter((o) => o.created_at?.startsWith(today));
    const pendingCount = orders.filter((o) => o.status === "pending" || o.status === "prep").length;
    const todayRevenue = todayOrders.reduce((s: number, o: any) => s + (o.total || 0), 0);

    const trends = aiData?.trends || {};
    const forecast = aiData?.forecast || [];
    const anomalies = aiData?.anomalies || [];
    const peakHour = trends.peak_hour;
    const peakDay = trends.peak_day;
    const wowGrowth = trends.week_over_week_growth;

    return (
        <div className="space-y-5">
            <div>
                <h1 className="text-xl font-bold text-[#e5e5e5]">Orders</h1>
                <p className="text-sm text-[#525252] mt-0.5">
                    Live from your POS &amp; KDS
                </p>
            </div>

            {/* Today at a glance */}
            <div className="grid grid-cols-3 gap-3">
                <div className="bg-[#141414] border border-[#262626] rounded-xl p-4">
                    <p className="text-xs text-[#525252]">Today&apos;s Sales</p>
                    <p className="text-lg font-bold text-[#22c55e] mt-1">{formatKES(todayRevenue)}</p>
                </div>
                <div className="bg-[#141414] border border-[#262626] rounded-xl p-4">
                    <p className="text-xs text-[#525252]">Orders</p>
                    <p className="text-lg font-bold text-[#e5e5e5] mt-1">{todayOrders.length}</p>
                </div>
                <div className="bg-[#141414] border border-[#262626] rounded-xl p-4">
                    <p className="text-xs text-[#525252]">In the Kitchen</p>
                    <p className="text-lg font-bold text-[#d4a853] mt-1">{pendingCount}</p>
                </div>
            </div>

            {/* What we're seeing with your sales */}
            {(trends.total_revenue || forecast.length > 0) && (
                <div className="bg-[#141414] border border-[#262626] rounded-xl">
                    <div className="px-4 py-3 border-b border-[#1a1a1a]">
                        <p className="text-xs font-semibold text-[#e5e5e5]">What we&apos;re seeing</p>
                    </div>
                    <div className="px-4 py-3 space-y-3">
                        {/* Natural language insights */}
                        <div className="space-y-2">
                            {trends.total_revenue > 0 && (
                                <p className="text-xs text-[#737373]">
                                    You&apos;ve made <span className="text-[#e5e5e5] font-semibold">{formatKES(trends.total_revenue)}</span> in the last 30 days
                                </p>
                            )}
                            {trends.avg_order_value > 0 && (
                                <p className="text-xs text-[#737373]">
                                    Customers spend about <span className="text-[#e5e5e5] font-semibold">{formatKES(trends.avg_order_value)}</span> per order on average
                                </p>
                            )}
                            {wowGrowth !== undefined && wowGrowth !== 0 && (
                                <p className="text-xs text-[#737373]">
                                    Compared to last week, sales are{" "}
                                    <span className={`font-semibold ${wowGrowth >= 0 ? "text-[#22c55e]" : "text-[#ef4444]"}`}>
                                        {wowGrowth > 0 ? "up" : "down"} {Math.abs(wowGrowth).toFixed(1)}%
                                    </span>
                                </p>
                            )}
                            {peakDay && (
                                <p className="text-xs text-[#737373]">
                                    Your busiest day is usually <span className="text-[#d4a853] font-semibold">{peakDay}</span>
                                    {peakHour !== undefined && (
                                        <>, and the rush comes around <span className="text-[#d4a853] font-semibold">{formatHour(peakHour)}</span></>
                                    )}
                                </p>
                            )}
                        </div>

                        {/* Next 7 days forecast */}
                        {forecast.length > 0 && (
                            <div>
                                <p className="text-[10px] text-[#525252] mb-2">Expected sales this coming week</p>
                                <div className="flex gap-1 items-end h-14">
                                    {forecast.map((f: any, i: number) => {
                                        const max = Math.max(...forecast.map((ff: any) => ff.predicted || ff.amount || 0));
                                        const val = f.predicted || f.amount || 0;
                                        const pct = max > 0 ? (val / max) * 100 : 0;
                                        return (
                                            <div key={i} className="flex-1 flex flex-col items-center gap-1">
                                                <div className="w-full rounded-sm relative overflow-hidden" style={{ height: `${Math.max(pct, 8)}%` }}>
                                                    <div className="absolute inset-0 bg-[#d4a853]/30 rounded-sm" />
                                                </div>
                                                <span className="text-[8px] text-[#525252]">{f.day_name?.slice(0, 3) || `Day ${i + 1}`}</span>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        )}

                        {/* Unusual days */}
                        {anomalies.length > 0 && (
                            <div className="space-y-1 pt-2 border-t border-[#1a1a1a]">
                                <p className="text-[10px] text-[#525252] uppercase tracking-wider">Unusual days we noticed</p>
                                {anomalies.slice(0, 2).map((a: any, i: number) => (
                                    <p key={i} className="text-xs text-[#737373]">
                                        {a.date}: sales were{" "}
                                        <span className={a.type === "high" ? "text-[#22c55e]" : "text-[#ef4444]"}>
                                            {a.type === "high" ? "higher than normal" : "lower than usual"}
                                        </span>
                                        {" "}at {formatKES(a.revenue)}
                                    </p>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Order List */}
            <div className="bg-[#141414] border border-[#262626] rounded-xl">
                <div className="px-4 py-3 border-b border-[#1a1a1a]">
                    <h2 className="text-sm font-semibold text-[#e5e5e5]">Recent Orders</h2>
                </div>
                {orders.length === 0 ? (
                    <div className="px-5 py-10 text-center">
                        <ShoppingBag className="w-8 h-8 text-[#333] mx-auto mb-3" />
                        <p className="text-sm text-[#525252]">No orders yet — they&apos;ll show up here from your POS</p>
                    </div>
                ) : (
                    <div className="divide-y divide-[#1a1a1a]">
                        {orders.map((order, i) => {
                            const statusLabels: Record<string, string> = {
                                pending: "Waiting",
                                prep: "Cooking",
                                ready: "Ready",
                                served: "Served",
                                cancelled: "Cancelled",
                            };
                            const statusStyles: Record<string, string> = {
                                pending: "bg-[#eab308]/10 text-[#eab308]",
                                prep: "bg-[#3b82f6]/10 text-[#3b82f6]",
                                ready: "bg-[#22c55e]/10 text-[#22c55e]",
                                served: "bg-[#737373]/10 text-[#737373]",
                                cancelled: "bg-[#ef4444]/10 text-[#ef4444]",
                            };
                            return (
                                <motion.div key={order.id || i} initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                                    transition={{ delay: i * 0.03 }}
                                    className="px-4 py-3 flex items-center justify-between hover:bg-[#1a1a1a] transition-colors">
                                    <div className="flex items-center gap-3">
                                        <span className="text-sm font-mono text-[#525252]">#{order.id}</span>
                                        <div>
                                            <p className="text-sm text-[#e5e5e5]">{order.customer_name || "Walk-in"}</p>
                                            <p className="text-xs text-[#525252] mt-0.5">
                                                {friendlyOrderType(order.order_type)}{order.table_number ? ` · Table ${order.table_number}` : ""}
                                            </p>
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <p className="text-sm font-medium text-[#d4a853]">{formatKES(order.total)}</p>
                                        <span className={`inline-block mt-1 px-2 py-0.5 rounded text-[10px] font-medium ${statusStyles[order.status] || statusStyles.pending}`}>
                                            {statusLabels[order.status] || order.status}
                                        </span>
                                    </div>
                                </motion.div>
                            );
                        })}
                    </div>
                )}
            </div>
        </div>
    );
}

function formatKES(cents: number) {
    if (!cents) return "KES 0";
    return `KES ${(cents / 100).toLocaleString("en-KE", { maximumFractionDigits: 0 })}`;
}

function formatHour(hour: number) {
    if (hour === 0) return "12 midnight";
    if (hour === 12) return "12 noon";
    return hour > 12 ? `${hour - 12}pm` : `${hour}am`;
}

function friendlyOrderType(type: string) {
    const map: Record<string, string> = {
        dine_in: "Dine in",
        takeout: "Takeaway",
        delivery: "Delivery",
    };
    return map[type] || type || "Dine in";
}
