"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { motion } from "framer-motion";
import { CalendarDays, DollarSign } from "lucide-react";

export default function ReservationsPage() {
    const [reservations, setReservations] = useState<any[]>([]);
    const [aiData, setAiData] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        Promise.all([
            api.get("/reservations/").catch(() => ({ data: [] })),
            api.get("/ai/reservation-insights").catch(() => ({ data: null })),
        ]).then(([resRes, aiRes]) => {
            setReservations(Array.isArray(resRes.data) ? resRes.data : []);
            setAiData(aiRes.data);
            setLoading(false);
        });
    }, []);

    if (loading) {
        return (
            <div className="space-y-3">
                {[...Array(4)].map((_, i) => (
                    <div key={i} className="bg-[#141414] rounded-xl h-16 animate-pulse" />
                ))}
            </div>
        );
    }

    const today = new Date().toISOString().split("T")[0];
    const todayBookings = reservations.filter((r) => r.reservation_date === today);
    const upcoming = reservations.filter((r) => r.reservation_date >= today && r.status === "confirmed");

    const noShow = aiData?.no_show_analysis || {};
    const revenue = aiData?.revenue_impact || {};
    const deposit = aiData?.deposit_effectiveness || {};
    const tables = aiData?.table_utilization || {};
    const recommendations = aiData?.recommendations || [];
    const overbooking = aiData?.overbooking || {};

    return (
        <div className="space-y-5">
            <div>
                <h1 className="text-xl font-bold text-[#e5e5e5]">Bookings</h1>
                <p className="text-sm text-[#525252] mt-0.5">
                    {todayBookings.length} today · {upcoming.length} coming up
                </p>
            </div>

            {/* Today at a glance */}
            <div className="grid grid-cols-3 gap-3">
                <div className="bg-[#141414] border border-[#262626] rounded-xl p-4">
                    <p className="text-xs text-[#525252]">Today</p>
                    <p className="text-lg font-bold text-[#d4a853] mt-1">{todayBookings.length}</p>
                </div>
                <div className="bg-[#141414] border border-[#262626] rounded-xl p-4">
                    <p className="text-xs text-[#525252]">Coming Up</p>
                    <p className="text-lg font-bold text-[#e5e5e5] mt-1">{upcoming.length}</p>
                </div>
                <div className="bg-[#141414] border border-[#262626] rounded-xl p-4">
                    <p className="text-xs text-[#525252]">Total</p>
                    <p className="text-lg font-bold text-[#737373] mt-1">{reservations.length}</p>
                </div>
            </div>

            {/* What we're seeing about bookings */}
            {(noShow.no_show_rate > 0 || revenue.estimated_revenue_lost > 0 || recommendations.length > 0) && (
                <div className="bg-[#141414] border border-[#262626] rounded-xl">
                    <div className="px-4 py-3 border-b border-[#1a1a1a]">
                        <p className="text-xs font-semibold text-[#e5e5e5]">What we&apos;re noticing</p>
                    </div>
                    <div className="px-4 py-3 space-y-3">
                        {/* Natural language insights */}
                        <div className="space-y-2">
                            {noShow.no_show_rate > 0 && (
                                <p className="text-xs text-[#737373]">
                                    About <span className="text-[#ef4444] font-semibold">{noShow.no_show_rate?.toFixed(0)}% of people who book don&apos;t show up</span>
                                </p>
                            )}
                            {revenue.estimated_revenue_lost > 0 && (
                                <p className="text-xs text-[#737373]">
                                    That&apos;s costing you roughly <span className="text-[#ef4444] font-semibold">{formatKES(revenue.estimated_revenue_lost)}</span> in lost sales
                                </p>
                            )}
                            {tables.avg_utilization > 0 && (
                                <p className="text-xs text-[#737373]">
                                    Your tables are being used about <span className="text-[#e5e5e5] font-semibold">{tables.avg_utilization?.toFixed(0)}% of the time</span>
                                </p>
                            )}
                            {deposit.with_deposit_no_show_rate !== undefined && deposit.without_deposit_no_show_rate !== undefined && (
                                <p className="text-xs text-[#737373]">
                                    When you collect a deposit, only <span className="text-[#22c55e] font-semibold">{deposit.with_deposit_no_show_rate?.toFixed(0)}% skip</span> compared to <span className="text-[#ef4444] font-semibold">{deposit.without_deposit_no_show_rate?.toFixed(0)}% without one</span>
                                </p>
                            )}
                        </div>

                        {/* Overbooking opportunity */}
                        {overbooking.recommended_rate > 0 && (
                            <div className="bg-[#d4a853]/5 border border-[#d4a853]/10 rounded-lg px-3 py-2">
                                <p className="text-xs text-[#e5e5e5] flex items-center gap-2">
                                    <DollarSign className="w-3 h-3 text-[#d4a853]" />
                                    You can safely take <span className="font-bold text-[#d4a853]">{overbooking.recommended_rate}% more bookings</span> to make up for no-shows — that&apos;s about <span className="font-bold text-[#d4a853]">{formatKES(overbooking.potential_monthly_recovery || 0)} extra per month</span>
                                </p>
                            </div>
                        )}

                        {/* Suggestions */}
                        {recommendations.length > 0 && (
                            <div className="space-y-1.5 pt-2 border-t border-[#1a1a1a]">
                                <p className="text-[10px] text-[#525252] uppercase tracking-wider">Suggestions</p>
                                {recommendations.slice(0, 3).map((rec: any, i: number) => (
                                    <div key={i} className="flex items-start gap-2 text-xs">
                                        <span className="text-[#d4a853] mt-0.5">💡</span>
                                        <div>
                                            <p className="text-[#e5e5e5]">{rec.message}</p>
                                            {rec.action && <p className="text-[#525252] mt-0.5">{rec.action}</p>}
                                            {rec.estimated_impact && (
                                                <p className="text-[10px] text-[#22c55e] mt-0.5">Could save you {rec.estimated_impact}</p>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Bookings List */}
            <div className="bg-[#141414] border border-[#262626] rounded-xl">
                {reservations.length === 0 ? (
                    <div className="px-5 py-10 text-center">
                        <CalendarDays className="w-8 h-8 text-[#333] mx-auto mb-3" />
                        <p className="text-sm text-[#525252]">No bookings yet — they&apos;ll come in from your booking system</p>
                    </div>
                ) : (
                    <>
                        <div className="px-4 py-3 border-b border-[#1a1a1a]">
                            <h2 className="text-sm font-semibold text-[#e5e5e5]">All Bookings</h2>
                        </div>
                        <div className="divide-y divide-[#1a1a1a]">
                            {reservations.map((res, i) => {
                                const statusLabels: Record<string, string> = {
                                    confirmed: "Confirmed",
                                    cancelled: "Cancelled",
                                    completed: "Done",
                                    no_show: "Didn't show",
                                };
                                const statusStyles: Record<string, string> = {
                                    confirmed: "bg-[#22c55e]/10 text-[#22c55e]",
                                    cancelled: "bg-[#ef4444]/10 text-[#ef4444]",
                                    completed: "bg-[#737373]/10 text-[#737373]",
                                    no_show: "bg-[#eab308]/10 text-[#eab308]",
                                };
                                return (
                                    <motion.div key={res.id || i} initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                                        transition={{ delay: i * 0.03 }}
                                        className="px-4 py-3 flex items-center justify-between hover:bg-[#1a1a1a] transition-colors">
                                        <div>
                                            <p className="text-sm text-[#e5e5e5]">{res.customer_name}</p>
                                            <p className="text-xs text-[#525252] mt-0.5">
                                                {res.party_size} guest{res.party_size !== 1 ? "s" : ""}{res.customer_phone && ` · ${res.customer_phone}`}
                                            </p>
                                        </div>
                                        <div className="text-right">
                                            <p className="text-sm text-[#737373]">{res.reservation_date}</p>
                                            <p className="text-xs text-[#525252] mt-0.5">{res.reservation_time}</p>
                                            <span className={`inline-block mt-1 px-2 py-0.5 rounded text-[10px] font-medium ${statusStyles[res.status] || statusStyles.confirmed}`}>
                                                {statusLabels[res.status] || res.status}
                                            </span>
                                        </div>
                                    </motion.div>
                                );
                            })}
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}

function formatKES(cents: number) {
    if (!cents) return "KES 0";
    return `KES ${(cents / 100).toLocaleString("en-KE", { maximumFractionDigits: 0 })}`;
}
