"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { motion } from "framer-motion";
import {
    UtensilsCrossed,
    TrendingUp,
    Package,
    CalendarDays,
    Clock,
    Zap,
    Wifi,
    Monitor,
    Smartphone,
    CreditCard,
} from "lucide-react";

export default function AIInsightsPage() {
    const [dashboard, setDashboard] = useState<any>(null);
    const [menu, setMenu] = useState<any>(null);
    const [revenue, setRevenue] = useState<any>(null);
    const [inventory, setInventory] = useState<any>(null);
    const [reservations, setReservations] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        Promise.all([
            api.get("/ai/dashboard").catch(() => ({ data: null })),
            api.get("/ai/menu-engineering").catch(() => ({ data: null })),
            api.get("/ai/revenue-forecast").catch(() => ({ data: null })),
            api.get("/ai/inventory-predictions").catch(() => ({ data: null })),
            api.get("/ai/reservation-insights").catch(() => ({ data: null })),
        ]).then(([d, m, r, i, res]) => {
            setDashboard(d.data);
            setMenu(m.data);
            setRevenue(r.data);
            setInventory(i.data);
            setReservations(res.data);
            setLoading(false);
        });
    }, []);

    if (loading) {
        return (
            <div className="space-y-4">
                <div className="bg-[#141414] rounded-xl h-28 animate-pulse" />
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {[...Array(4)].map((_, i) => (
                        <div key={i} className="bg-[#141414] rounded-xl h-44 animate-pulse" />
                    ))}
                </div>
            </div>
        );
    }

    const healthScore = dashboard?.health_score ?? 0;
    const breakdown = dashboard?.health_breakdown || [];
    const menuSummary = menu?.summary || {};
    const menuRecs = menu?.recommendations || [];
    const revTrends = revenue?.trends || {};
    const invSummary = inventory?.summary || {};
    const invAlerts = inventory?.alerts || [];
    const noShow = reservations?.no_show_analysis || {};
    const revImpact = reservations?.revenue_impact || {};
    const resRecs = reservations?.recommendations || [];

    const healthLabel = healthScore >= 80 ? "Your restaurant is running really well" :
        healthScore >= 60 ? "Things are okay — a few areas could be better" :
            healthScore >= 40 ? "There are some issues we should sort out" :
                "Your restaurant needs attention on a few fronts";

    const allRecs = [
        ...menuRecs.map((r: any) => ({ ...r, source: "Menu", text: r.reason || r.message })),
        ...invAlerts.map((r: any) => ({ ...r, source: "Stock", text: r.message })),
        ...resRecs.map((r: any) => ({ ...r, source: "Bookings", text: r.message })),
    ];

    return (
        <div className="space-y-5">
            {/* Header */}
            <div>
                <h1 className="text-xl font-bold text-[#e5e5e5]">Insights</h1>
                <p className="text-sm text-[#525252] mt-0.5">
                    Everything your systems are telling us right now
                </p>
            </div>

            {/* How your restaurant is doing */}
            <div className="bg-gradient-to-r from-[#22c55e]/5 to-[#d4a853]/5 border border-[#262626] rounded-xl p-5">
                <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                    <div className="flex items-center gap-3 flex-1">
                        <div className="relative">
                            <span className="flex h-3 w-3">
                                <span className="animate-ping absolute h-3 w-3 rounded-full bg-[#22c55e] opacity-75" />
                                <span className="relative rounded-full h-3 w-3 bg-[#22c55e]" />
                            </span>
                        </div>
                        <div>
                            <p className="text-sm font-semibold text-[#e5e5e5]">{healthLabel}</p>
                            <p className="text-xs text-[#525252] mt-0.5">
                                Watching your menu, sales, kitchen, stock &amp; bookings — all day, every day
                            </p>
                        </div>
                    </div>
                    <div className="text-right">
                        <p className={`text-3xl font-bold ${healthScore >= 70 ? "text-[#22c55e]" : healthScore >= 40 ? "text-[#eab308]" : "text-[#ef4444]"
                            }`}>{healthScore}<span className="text-lg text-[#525252]">/100</span></p>
                    </div>
                </div>

                {/* Connected systems */}
                <div className="flex flex-wrap gap-3 mt-4 pt-3 border-t border-[#262626]">
                    <SystemPill icon={Monitor} label="POS" />
                    <SystemPill icon={Smartphone} label="KDS" />
                    <SystemPill icon={Package} label="Inventory" />
                    <SystemPill icon={CalendarDays} label="Bookings" />
                    <SystemPill icon={CreditCard} label="Payments" />
                </div>
            </div>

            {/* The 5 areas we're watching */}
            <div>
                <p className="text-xs font-semibold text-[#525252] uppercase tracking-wider mb-3 px-1">What each area looks like</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {/* Menu */}
                    <AreaCard
                        icon={UtensilsCrossed}
                        name="Your Menu"
                        color="#22c55e"
                        score={breakdown.find((b: any) => b.category === "Menu Health")?.score}
                        insights={[
                            menuSummary.stars > 0 && `${menuSummary.stars} top seller${menuSummary.stars > 1 ? "s" : ""} doing great`,
                            menuSummary.puzzles > 0 && `${menuSummary.puzzles} item${menuSummary.puzzles > 1 ? "s" : ""} with good margins that could sell more`,
                            menuSummary.dogs > 0 && `${menuSummary.dogs} item${menuSummary.dogs > 1 ? "s" : ""} you should think about removing`,
                            menuSummary.avg_food_cost_pct > 0 && `Food costs are around ${menuSummary.avg_food_cost_pct.toFixed(0)}% of your prices`,
                        ].filter(Boolean) as string[]}
                        recs={menuRecs.slice(0, 2).map(friendlyMenuRec)}
                    />

                    {/* Revenue */}
                    <AreaCard
                        icon={TrendingUp}
                        name="Sales Trend"
                        color="#d4a853"
                        score={breakdown.find((b: any) => b.category === "Revenue Trend")?.score}
                        insights={[
                            revTrends.total_revenue > 0 && `${formatKES(revTrends.total_revenue)} in the last 30 days`,
                            revTrends.avg_order_value > 0 && `Customers spend about ${formatKES(revTrends.avg_order_value)} per order`,
                            revTrends.week_over_week_growth !== undefined && `${revTrends.week_over_week_growth >= 0 ? "Up" : "Down"} ${Math.abs(revTrends.week_over_week_growth).toFixed(1)}% from last week`,
                            revTrends.peak_day && `Busiest day is usually ${revTrends.peak_day}`,
                        ].filter(Boolean) as string[]}
                        recs={[]}
                    />

                    {/* Kitchen */}
                    <AreaCard
                        icon={Clock}
                        name="Kitchen Speed"
                        color="#3b82f6"
                        score={breakdown.find((b: any) => b.category === "Kitchen Efficiency")?.score}
                        insights={[
                            "Connected to your KDS — tracking prep times",
                            "Monitoring order throughput by station",
                        ]}
                        recs={[]}
                    />

                    {/* Stock */}
                    <AreaCard
                        icon={Package}
                        name="Stock Levels"
                        color="#eab308"
                        score={breakdown.find((b: any) => b.category === "Inventory Status")?.score}
                        insights={[
                            invSummary.critical_items > 0 && `${invSummary.critical_items} item${invSummary.critical_items > 1 ? "s have" : " has"} run out`,
                            invSummary.low_stock_items > 0 && `${invSummary.low_stock_items} item${invSummary.low_stock_items > 1 ? "s" : ""} running low`,
                            invSummary.high_spoilage_items > 0 && `${invSummary.high_spoilage_items} item${invSummary.high_spoilage_items > 1 ? "s" : ""} might spoil soon`,
                            invSummary.monthly_spend > 0 && `Spending about ${formatKES(invSummary.monthly_spend)}/month on stock`,
                        ].filter(Boolean) as string[]}
                        recs={invAlerts.slice(0, 2).map((a: any) => a.message)}
                    />

                    {/* Bookings */}
                    <AreaCard
                        icon={CalendarDays}
                        name="Bookings"
                        color="#ef4444"
                        score={breakdown.find((b: any) => b.category === "Reservation Reliability")?.score}
                        insights={[
                            noShow.no_show_rate > 0 && `${noShow.no_show_rate?.toFixed(0)}% of bookings are no-shows`,
                            revImpact.estimated_revenue_lost > 0 && `That's losing you about ${formatKES(revImpact.estimated_revenue_lost)}`,
                        ].filter(Boolean) as string[]}
                        recs={resRecs.slice(0, 2).map((r: any) => r.message)}
                    />
                </div>
            </div>

            {/* All Suggestions */}
            {allRecs.length > 0 && (
                <div className="bg-[#141414] border border-[#262626] rounded-xl">
                    <div className="px-4 py-3 border-b border-[#1a1a1a] flex items-center gap-2">
                        <Zap className="w-3.5 h-3.5 text-[#d4a853]" />
                        <h2 className="text-sm font-semibold text-[#e5e5e5]">All Suggestions</h2>
                        <span className="text-[10px] text-[#525252] ml-auto">{allRecs.length} ideas</span>
                    </div>
                    <div className="divide-y divide-[#1a1a1a] max-h-80 overflow-y-auto">
                        {allRecs.slice(0, 12).map((rec: any, i: number) => {
                            const sourceColors: Record<string, string> = {
                                Menu: "bg-[#22c55e]/10 text-[#22c55e]",
                                Stock: "bg-[#eab308]/10 text-[#eab308]",
                                Bookings: "bg-[#ef4444]/10 text-[#ef4444]",
                            };
                            return (
                                <motion.div key={i} initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                                    transition={{ delay: i * 0.03 }}
                                    className="px-4 py-3 flex items-start gap-3">
                                    <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded mt-0.5 flex-shrink-0 ${sourceColors[rec.source] || "bg-[#737373]/10 text-[#737373]"
                                        }`}>{rec.source}</span>
                                    <div>
                                        <p className="text-sm text-[#e5e5e5]">
                                            {friendlyText(rec.text)}
                                        </p>
                                        {rec.action && <p className="text-xs text-[#d4a853] mt-0.5">→ {rec.action}</p>}
                                        {rec.estimated_impact && (
                                            <p className="text-[10px] text-[#22c55e] mt-0.5">💰 Could mean {rec.estimated_impact}</p>
                                        )}
                                    </div>
                                </motion.div>
                            );
                        })}
                    </div>
                </div>
            )}
        </div>
    );
}

/* Components */
function SystemPill({ icon: Icon, label }: { icon: any; label: string }) {
    return (
        <div className="flex items-center gap-1.5 px-2.5 py-1 bg-[#1a1a1a] rounded-full">
            <Icon className="w-3 h-3 text-[#525252]" />
            <span className="text-[10px] text-[#737373]">{label}</span>
            <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e]" />
        </div>
    );
}

function AreaCard({ icon: Icon, name, color, score, insights, recs }: {
    icon: any; name: string; color: string; score?: number;
    insights: string[]; recs: string[];
}) {
    return (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            className="bg-[#141414] border border-[#262626] rounded-xl">
            <div className="px-4 py-3 border-b border-[#1a1a1a] flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Icon className="w-3.5 h-3.5" style={{ color }} />
                    <span className="text-xs font-semibold text-[#e5e5e5]">{name}</span>
                </div>
                {score !== undefined && (
                    <span className={`text-xs font-bold ${score >= 70 ? "text-[#22c55e]" : score >= 40 ? "text-[#eab308]" : "text-[#ef4444]"
                        }`}>{score >= 70 ? "Good" : score >= 40 ? "Okay" : "Needs work"}</span>
                )}
            </div>
            <div className="px-4 py-3 space-y-2">
                {insights.length > 0 ? (
                    <div className="space-y-1">
                        {insights.map((insight, i) => (
                            <p key={i} className="text-xs text-[#737373]">• {insight}</p>
                        ))}
                    </div>
                ) : (
                    <p className="text-xs text-[#525252]">Collecting data...</p>
                )}
                {recs.length > 0 && (
                    <div className="space-y-1 pt-2 border-t border-[#1a1a1a]">
                        {recs.map((rec: string, i: number) => (
                            <p key={i} className="text-[10px] text-[#d4a853]">
                                💡 {friendlyText(rec)}
                            </p>
                        ))}
                    </div>
                )}
            </div>
        </motion.div>
    );
}

/* Helpers */
function formatKES(cents: number) {
    if (!cents) return "KES 0";
    return `KES ${(cents / 100).toLocaleString("en-KE", { maximumFractionDigits: 0 })}`;
}

function friendlyText(text: string) {
    return text
        .replace(/Star items?/gi, "top seller")
        .replace(/Plowhorse items?/gi, "popular item")
        .replace(/Puzzle items?/gi, "hidden gem")
        .replace(/Dog items?/gi, "slow mover")
        .replace(/Stars/gi, "top sellers")
        .replace(/Plowhorses/gi, "popular items")
        .replace(/Puzzles/gi, "hidden gems")
        .replace(/Dogs/gi, "slow movers");
}

function friendlyMenuRec(rec: any): string {
    return friendlyText(rec.reason || rec.message || "");
}
