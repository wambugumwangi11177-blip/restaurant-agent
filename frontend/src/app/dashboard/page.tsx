"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import { motion } from "framer-motion";
import {
    TrendingUp,
    ShoppingBag,
    AlertTriangle,
    Activity,
    Zap,
    Shield,
    Wifi,
    Monitor,
    Smartphone,
} from "lucide-react";

export default function DashboardPage() {
    const { user } = useAuth();
    const [data, setData] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get("/ai/dashboard")
            .then((r) => setData(r.data))
            .catch(() => { })
            .finally(() => setLoading(false));
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
                <div className="bg-[#141414] rounded-xl h-24 animate-pulse" />
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                    {[...Array(4)].map((_, i) => (
                        <div key={i} className="bg-[#141414] rounded-xl h-24 animate-pulse" />
                    ))}
                </div>
            </div>
        );
    }

    const qs = data?.quick_stats || {};
    const healthScore = data?.health_score ?? 0;
    const breakdown = data?.health_breakdown || [];
    const alerts = data?.alerts || [];
    const risks = data?.risks || [];
    const opportunities = data?.opportunities || [];

    const healthLabel = healthScore >= 80 ? "Looking great" : healthScore >= 60 ? "Doing okay" : healthScore >= 40 ? "Needs attention" : "Let's fix a few things";

    return (
        <div className="space-y-5">
            {/* Greeting */}
            <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                <div>
                    <h1 className="text-xl font-bold text-[#e5e5e5]">
                        {getGreeting()} 👋
                    </h1>
                    <p className="text-sm text-[#525252] mt-1">
                        Here&apos;s how your restaurant is doing right now
                    </p>
                </div>
                {/* Health Score */}
                <motion.div
                    initial={{ scale: 0.8, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    className="flex items-center gap-3 bg-[#141414] border border-[#262626] rounded-xl px-4 py-3"
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
                        <span className="absolute inset-0 flex items-center justify-center text-sm font-bold text-[#e5e5e5]">
                            {healthScore}
                        </span>
                    </div>
                    <div>
                        <p className="text-sm font-semibold text-[#e5e5e5]">Overall Health</p>
                        <p className="text-xs text-[#525252]">{healthLabel}</p>
                    </div>
                </motion.div>
            </div>

            {/* Connected Systems */}
            <div className="bg-[#141414] border border-[#262626] rounded-xl px-4 py-3">
                <div className="flex items-center gap-2 mb-2">
                    <span className="flex h-2 w-2">
                        <span className="animate-ping absolute h-2 w-2 rounded-full bg-[#22c55e] opacity-75" />
                        <span className="relative rounded-full h-2 w-2 bg-[#22c55e]" />
                    </span>
                    <span className="text-xs font-medium text-[#22c55e]">Systems Connected</span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                    <SystemStatus icon={Monitor} label="POS" status="connected" />
                    <SystemStatus icon={Smartphone} label="KDS" status="connected" />
                    <SystemStatus icon={ShoppingBag} label="Orders" status="connected" />
                    <SystemStatus icon={Activity} label="Inventory" status="connected" />
                    <SystemStatus icon={Wifi} label="Payments" status="connected" />
                </div>
            </div>

            {/* What's happening at a glance */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <StatCard
                    label="Today's Sales"
                    value={formatKES(qs.today_revenue)}
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
                    value={formatKES(qs.avg_order_value)}
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
            <div className="bg-[#141414] border border-[#262626] rounded-xl px-4 py-3">
                <p className="text-xs font-semibold text-[#e5e5e5] mb-3">How each area is doing</p>
                <div className="space-y-2">
                    {breakdown.map((b: any, i: number) => {
                        const friendlyNames: Record<string, string> = {
                            "Menu Health": "Your Menu",
                            "Revenue Trend": "Sales Trend",
                            "Kitchen Efficiency": "Kitchen Speed",
                            "Inventory Status": "Stock Levels",
                            "Reservation Reliability": "Bookings",
                        };
                        return (
                            <div key={i} className="flex items-center gap-3">
                                <span className="text-xs text-[#737373] w-28 flex-shrink-0">
                                    {friendlyNames[b.category] || b.category}
                                </span>
                                <div className="flex-1 h-2 bg-[#1a1a1a] rounded-full overflow-hidden">
                                    <motion.div
                                        initial={{ width: 0 }}
                                        animate={{ width: `${b.score}%` }}
                                        transition={{ delay: i * 0.1, duration: 0.5 }}
                                        className={`h-full rounded-full ${b.score >= 70 ? "bg-[#22c55e]" : b.score >= 40 ? "bg-[#eab308]" : "bg-[#ef4444]"
                                            }`}
                                    />
                                </div>
                                <span className={`text-xs font-medium w-10 text-right ${b.score >= 70 ? "text-[#22c55e]" : b.score >= 40 ? "text-[#eab308]" : "text-[#ef4444]"
                                    }`}>{b.score}%</span>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* Risks & Opportunities side by side */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                {/* Watch out for */}
                <div className="bg-[#141414] border border-[#262626] rounded-xl">
                    <div className="px-4 py-3 border-b border-[#1a1a1a] flex items-center gap-2">
                        <Shield className="w-3.5 h-3.5 text-[#ef4444]" />
                        <h2 className="text-sm font-semibold text-[#e5e5e5]">Watch Out For</h2>
                    </div>
                    {risks.length === 0 ? (
                        <div className="px-4 py-6 text-center text-xs text-[#525252]">Everything looks good right now ✓</div>
                    ) : (
                        <div className="divide-y divide-[#1a1a1a]">
                            {risks.map((r: any, i: number) => (
                                <motion.div key={i} initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                                    transition={{ delay: i * 0.05 }} className="px-4 py-3">
                                    <div className="flex items-center gap-2">
                                        <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${r.severity === "critical" ? "bg-[#ef4444]/10 text-[#ef4444]"
                                                : r.severity === "high" ? "bg-[#eab308]/10 text-[#eab308]"
                                                    : "bg-[#3b82f6]/10 text-[#3b82f6]"
                                            }`}>{r.severity === "critical" ? "urgent" : r.severity}</span>
                                        <p className="text-sm text-[#e5e5e5]">{friendlyRisk(r.risk)}</p>
                                    </div>
                                    <p className="text-xs text-[#525252] mt-1">{friendlyDetail(r.detail)}</p>
                                </motion.div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Ways to earn more */}
                <div className="bg-[#141414] border border-[#262626] rounded-xl">
                    <div className="px-4 py-3 border-b border-[#1a1a1a] flex items-center gap-2">
                        <Zap className="w-3.5 h-3.5 text-[#d4a853]" />
                        <h2 className="text-sm font-semibold text-[#e5e5e5]">Ways to Earn More</h2>
                    </div>
                    {opportunities.length === 0 ? (
                        <div className="px-4 py-6 text-center text-xs text-[#525252]">We&apos;re looking for opportunities...</div>
                    ) : (
                        <div className="divide-y divide-[#1a1a1a]">
                            {opportunities.map((o: any, i: number) => (
                                <motion.div key={i} initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                                    transition={{ delay: i * 0.05 }} className="px-4 py-3">
                                    <div className="flex items-center gap-2">
                                        <Zap className="w-3 h-3 text-[#d4a853]" />
                                        <p className="text-sm text-[#e5e5e5]">{friendlyOpportunity(o.opportunity)}</p>
                                    </div>
                                    <p className="text-xs text-[#525252] mt-1">{friendlyDetail(o.detail)}</p>
                                </motion.div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* Alerts */}
            {alerts.length > 0 && (
                <div className="bg-[#141414] border border-[#262626] rounded-xl">
                    <div className="px-4 py-3 border-b border-[#1a1a1a] flex items-center gap-2">
                        <AlertTriangle className="w-3.5 h-3.5 text-[#eab308]" />
                        <h2 className="text-sm font-semibold text-[#e5e5e5]">Alerts From Your Systems</h2>
                        <span className="text-[10px] text-[#525252] ml-auto">{alerts.length} active</span>
                    </div>
                    <div className="divide-y divide-[#1a1a1a] max-h-64 overflow-y-auto">
                        {alerts.map((a: any, i: number) => {
                            const sourceLabels: Record<string, string> = {
                                inventory: "Stock", kitchen: "Kitchen", menu: "Menu", reservations: "Bookings",
                            };
                            return (
                                <div key={i} className="px-4 py-3 flex items-start gap-3">
                                    <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded mt-0.5 flex-shrink-0 ${a.source === "inventory" ? "bg-[#ef4444]/10 text-[#ef4444]"
                                            : a.source === "kitchen" ? "bg-[#eab308]/10 text-[#eab308]"
                                                : a.source === "menu" ? "bg-[#3b82f6]/10 text-[#3b82f6]"
                                                    : "bg-[#8b5cf6]/10 text-[#8b5cf6]"
                                        }`}>{sourceLabels[a.source] || a.source}</span>
                                    <div>
                                        <p className="text-sm text-[#e5e5e5]">{a.message}</p>
                                        {a.action && (
                                            <p className="text-xs text-[#d4a853] mt-1">💡 {a.action}</p>
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

/* Helper Components */
function SystemStatus({ icon: Icon, label, status }: { icon: any; label: string; status: string }) {
    return (
        <div className="flex items-center gap-2">
            <Icon className="w-3 h-3 text-[#525252]" />
            <span className="text-xs text-[#737373]">{label}</span>
            <span className={`w-1.5 h-1.5 rounded-full ml-auto ${status === "connected" ? "bg-[#22c55e]" : "bg-[#ef4444]"
                }`} />
        </div>
    );
}

function StatCard({ label, value, sub, color }: { label: string; value: any; sub?: string; color: string; }) {
    return (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            className="bg-[#141414] border border-[#262626] rounded-xl p-4">
            <p className="text-lg font-bold text-[#e5e5e5]">{value}</p>
            <p className="text-xs text-[#525252] mt-0.5">{label}</p>
            {sub && <p className="text-[10px] mt-1" style={{ color }}>{sub}</p>}
        </motion.div>
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
