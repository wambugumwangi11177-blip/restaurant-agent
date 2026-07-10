"use client";

/**
 * /dashboard/roi — Time & Money Saved
 *
 * Pitch-facing ROI view: how many staff hours the software automated away
 * (converted to money via this restaurant's own wage data), extra profit
 * already captured via approved pricing recommendations, and opportunities
 * the AI has flagged but the owner hasn't acted on yet.
 *
 * Mirrors the shape of GET /ai/roi (backend/ai/roi/savings.py) — three
 * distinct totals, deliberately never summed into one number: time-saved
 * money is an automation estimate, captured money already happened, and
 * opportunities are forward-looking and unrealized.
 */

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Clock, TrendingUp, Target, RefreshCw, AlertTriangle, Zap, ChefHat } from "lucide-react";

interface RoiBreakdownItem {
    category: string;
    count: number;
    minutes_per_action: number;
    total_minutes: number;
}

interface RoiData {
    window_days: number;
    time_saved: {
        hours_saved_30d: number;
        money_saved_cents: number;
        avg_hourly_rate_cents: number;
        hourly_rate_is_estimated: boolean;
        breakdown: RoiBreakdownItem[];
    };
    money_captured: {
        monthly_impact_cents: number;
        recommendations_approved: number;
    };
    opportunities: { source: string; label: string; monthly_value_cents: number }[];
    capacity: {
        avg_order_minutes: number;
        orders_per_day: number;
        bottlenecks_found: number;
        reclaimable_delay_minutes: number;
    } | null;
    narrative?: { headline: string; priorities: string[]; actions: { action: string; why: string; impact: string }[] };
    error?: string;
}

function formatKES(cents: number) {
    if (!cents) return "KES 0";
    return `KES ${(cents / 100).toLocaleString("en-KE", { maximumFractionDigits: 0 })}`;
}

const CATEGORY_LABELS: Record<string, string> = {
    morning_briefing: "Morning briefings sent",
    reservation_reminder: "Reservation reminders sent",
    no_show_winback: "No-show win-back messages",
    receipt: "Receipts sent",
    promo: "Promo messages sent",
    campaign_winback: "Win-back campaign messages",
    feedback_alert: "Feedback alerts handled",
    slow_day_alert: "Slow-day alerts sent",
    reorder_request: "Reorder requests sent",
    supplier_late: "Supplier delay alerts",
    stock_depleted: "Stock-out alerts",
    orchestrated_stock_critical: "Critical stock alerts",
    pricing_intelligence: "Pricing analysis runs",
    labor_intelligence: "Labor analysis runs",
    profit_intelligence: "Profit analysis runs",
    inventory_predictor: "Inventory analysis runs",
    supply_chain_intelligence: "Supplier analysis runs",
};

function EmptyState() {
    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-[#e5e5e5]">Time & Money Saved</h1>
                <p className="text-[#525252] mt-1 text-sm">Getting started</p>
            </div>
            <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-8 text-center space-y-4">
                <Clock className="w-12 h-12 text-[#d4a853] mx-auto" />
                <h2 className="text-[#e5e5e5] font-semibold text-lg">No automation activity yet</h2>
                <p className="text-[#525252] text-sm max-w-md mx-auto">
                    Once the AI starts sending WhatsApp messages, running analysis, or
                    you approve a pricing recommendation, this page will show exactly
                    how many hours and how much money it's saved you.
                </p>
            </div>
        </div>
    );
}

export default function RoiDashboard() {
    const { user } = useAuth();
    const [data, setData] = useState<RoiData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

    const restaurantName = (user as any)?.restaurant_name || "Your Restaurant";

    const fetchData = async () => {
        setLoading(true);
        setError("");
        try {
            const res = await api.get("/ai/roi");
            setData(res.data);
            setLastUpdated(new Date());
        } catch (e: any) {
            setError(e?.response?.data?.detail || e?.message || "Could not load ROI data");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchData(); }, []);

    if (loading) {
        return (
            <div className="space-y-4">
                <div className="bg-[#141414] rounded-xl h-8 w-48 animate-pulse" />
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {[...Array(3)].map((_, i) => (
                        <div key={i} className="bg-[#141414] rounded-xl h-32 animate-pulse" />
                    ))}
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[50vh] space-y-4">
                <AlertTriangle className="w-10 h-10 text-amber-400" />
                <p className="text-[#e5e5e5] font-medium">Could not load ROI data</p>
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

    const isEmpty =
        !data ||
        (data.time_saved.hours_saved_30d === 0 &&
            data.money_captured.monthly_impact_cents === 0 &&
            data.opportunities.length === 0 &&
            !data.capacity);
    if (isEmpty) {
        return <EmptyState />;
    }

    const ts = data!.time_saved;
    const mc = data!.money_captured;
    const opps = data!.opportunities;
    const cap = data!.capacity;
    const oppsTotal = opps.reduce((sum, o) => sum + o.monthly_value_cents, 0);

    return (
        <div className="space-y-6">
            <div className="flex items-start justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-[#e5e5e5]">Time & Money Saved</h1>
                    <p className="text-[#525252] mt-1 text-sm">
                        {restaurantName} — last {data!.window_days} days
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

            {/* Hero stats — three distinct totals, never summed */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-6">
                    <div className="flex items-center gap-2 text-emerald-400 mb-2">
                        <Clock className="w-4 h-4" />
                        <p className="text-xs uppercase tracking-widest">Time saved</p>
                    </div>
                    <p className="text-3xl font-black text-[#e5e5e5]">{ts.hours_saved_30d} hrs</p>
                    <p className="text-[#525252] text-sm mt-1">
                        ≈ {formatKES(ts.money_saved_cents)}
                        {ts.hourly_rate_is_estimated ? " (estimated wage)" : " (your staff wages)"}
                    </p>
                </div>

                <div className="rounded-xl border border-[#d4a853]/30 bg-[#d4a853]/5 p-6">
                    <div className="flex items-center gap-2 text-[#d4a853] mb-2">
                        <TrendingUp className="w-4 h-4" />
                        <p className="text-xs uppercase tracking-widest">Profit captured</p>
                    </div>
                    <p className="text-3xl font-black text-[#e5e5e5]">{formatKES(mc.monthly_impact_cents)}</p>
                    <p className="text-[#525252] text-sm mt-1">
                        from {mc.recommendations_approved} approved pricing recommendation
                        {mc.recommendations_approved === 1 ? "" : "s"}
                    </p>
                </div>

                <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-6">
                    <div className="flex items-center gap-2 text-amber-400 mb-2">
                        <Target className="w-4 h-4" />
                        <p className="text-xs uppercase tracking-widest">Opportunities flagged</p>
                    </div>
                    <p className="text-3xl font-black text-[#e5e5e5]">{formatKES(oppsTotal)}</p>
                    <p className="text-[#525252] text-sm mt-1">not yet acted on</p>
                </div>
            </div>

            {data!.narrative && (
                <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
                    <div className="flex items-center gap-2 text-[#d4a853] mb-2">
                        <Zap className="w-4 h-4" />
                        <p className="text-sm font-semibold text-[#e5e5e5]">{data!.narrative.headline}</p>
                    </div>
                    <ul className="text-sm text-[#a3a3a3] space-y-1 list-disc list-inside">
                        {data!.narrative.priorities.map((p, i) => <li key={i}>{p}</li>)}
                    </ul>
                </div>
            )}

            {/* Time-saved breakdown */}
            <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
                <p className="text-[#e5e5e5] font-semibold text-sm mb-4">
                    Where the {ts.hours_saved_30d} hours came from
                </p>
                {ts.breakdown.length === 0 ? (
                    <p className="text-[#525252] text-sm">No automated activity in this window.</p>
                ) : (
                    <div className="space-y-2">
                        {ts.breakdown.map((b, i) => (
                            <div key={i} className="flex items-center justify-between text-sm py-2 border-b border-[#1a1a1a] last:border-0">
                                <span className="text-[#a3a3a3]">
                                    {CATEGORY_LABELS[b.category] || b.category}
                                    <span className="text-[#525252]"> · {b.count}× at {b.minutes_per_action} min</span>
                                </span>
                                <span className="text-[#e5e5e5] font-medium">{Math.round(b.total_minutes / 60 * 10) / 10} hrs</span>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Opportunities breakdown */}
            {opps.length > 0 && (
                <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
                    <p className="text-[#e5e5e5] font-semibold text-sm mb-1">Money on the table the AI has found</p>
                    <p className="text-[#525252] text-xs mb-4">Flagged but not yet acted on — approve or action these to capture it.</p>
                    <div className="space-y-2">
                        {opps.map((o, i) => (
                            <div key={i} className="flex items-center justify-between text-sm py-2 border-b border-[#1a1a1a] last:border-0">
                                <span className="text-[#a3a3a3]">{o.label}</span>
                                <span className="text-amber-400 font-medium">{formatKES(o.monthly_value_cents)}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Kitchen capacity — non-monetary "do more with the same staff" story */}
            {cap && (
                <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
                    <div className="flex items-center gap-2 text-[#e5e5e5] mb-1">
                        <ChefHat className="w-4 h-4 text-[#d4a853]" />
                        <p className="font-semibold text-sm">Kitchen capacity</p>
                    </div>
                    <p className="text-[#525252] text-xs mb-4">
                        Serve more covers with the same staff — not counted as money above.
                    </p>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div>
                            <p className="text-2xl font-bold text-[#e5e5e5]">{cap.avg_order_minutes}<span className="text-sm text-[#525252]"> min</span></p>
                            <p className="text-[#525252] text-xs mt-1">avg order time</p>
                        </div>
                        <div>
                            <p className="text-2xl font-bold text-[#e5e5e5]">{cap.orders_per_day}</p>
                            <p className="text-[#525252] text-xs mt-1">orders / day</p>
                        </div>
                        <div>
                            <p className="text-2xl font-bold text-[#e5e5e5]">{cap.bottlenecks_found}</p>
                            <p className="text-[#525252] text-xs mt-1">bottlenecks flagged</p>
                        </div>
                        <div>
                            <p className="text-2xl font-bold text-[#e5e5e5]">{cap.reclaimable_delay_minutes}<span className="text-sm text-[#525252]"> min</span></p>
                            <p className="text-[#525252] text-xs mt-1">reclaimable delay</p>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
