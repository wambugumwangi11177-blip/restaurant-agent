"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { motion, AnimatePresence } from "framer-motion";
import { CalendarDays, DollarSign, Plus, X, Check } from "lucide-react";

/**
 * Bookings workspace — extends the original dashboard/reservations/page.tsx
 * (which was read-only despite the backend supporting create/status-update)
 * with an actual create form and status actions. Every tier with
 * `reservations` = RW (directive 015: Owner, Manager, Supervisor, Waiter)
 * reuses this unmodified; the write actions simply 403 server-side for a
 * tier without access, but no tier without `reservations` access at all
 * renders this component in the first place.
 */
export default function ReservationsWorkspace() {
    const [reservations, setReservations] = useState<any[]>([]);
    const [aiData, setAiData] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [submitting, setSubmitting] = useState(false);
    const [toast, setToast] = useState("");
    const [showForm, setShowForm] = useState(false);

    const [customerName, setCustomerName] = useState("");
    const [customerPhone, setCustomerPhone] = useState("");
    const [partySize, setPartySize] = useState("2");
    const [reservationDate, setReservationDate] = useState("");
    const [reservationTime, setReservationTime] = useState("");
    const [notes, setNotes] = useState("");

    const showToast = (msg: string) => {
        setToast(msg);
        setTimeout(() => setToast(""), 3000);
    };

    const fetchData = async () => {
        const [resRes, aiRes] = await Promise.all([
            api.get("/reservations/").catch(() => ({ data: [] })),
            api.get("/ai/reservation-insights").catch(() => ({ data: null })),
        ]);
        setReservations(Array.isArray(resRes.data) ? resRes.data : []);
        setAiData(aiRes.data);
        setLoading(false);
    };

    useEffect(() => { fetchData(); }, []);

    const resetForm = () => {
        setCustomerName(""); setCustomerPhone(""); setPartySize("2");
        setReservationDate(""); setReservationTime(""); setNotes("");
    };

    const handleCreate = async () => {
        if (!customerName || !reservationDate || !reservationTime) return;
        setSubmitting(true);
        try {
            await api.post("/reservations/", {
                customer_name: customerName,
                customer_phone: customerPhone,
                party_size: parseInt(partySize) || 2,
                reservation_date: reservationDate,
                reservation_time: reservationTime,
                notes,
            });
            showToast(`Booked for ${customerName}`);
            setShowForm(false);
            resetForm();
            await fetchData();
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to create booking");
        }
        setSubmitting(false);
    };

    const handleStatusChange = async (id: number, status: string) => {
        setSubmitting(true);
        try {
            await api.patch(`/reservations/${id}/status`, { status });
            await fetchData();
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to update booking");
        }
        setSubmitting(false);
    };

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
        <div className="space-y-5">
            <AnimatePresence>
                {toast && (
                    <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}
                        className="fixed top-4 right-4 z-50 bg-[#22c55e]/10 border border-[#22c55e]/30 rounded-xl px-5 py-3 flex items-center gap-2">
                        <Check className="w-4 h-4 text-[#22c55e]" />
                        <span className="text-sm text-[#22c55e]">{toast}</span>
                    </motion.div>
                )}
            </AnimatePresence>

            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-xl font-bold text-[#e5e5e5]">Bookings</h1>
                    <p className="text-sm text-[#525252] mt-0.5">
                        {todayBookings.length} today · {upcoming.length} coming up
                    </p>
                </div>
                <button onClick={() => setShowForm(!showForm)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--accent)]/10 border border-[var(--accent)]/30 rounded-lg text-xs text-[var(--accent)] hover:bg-[var(--accent)]/20 transition-all">
                    <Plus className="w-3 h-3" />
                    New Booking
                </button>
            </div>

            <AnimatePresence>
                {showForm && (
                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                        className="bg-[#141414] border border-[var(--accent)]/20 rounded-xl overflow-hidden">
                        <div className="px-4 py-3 border-b border-[#1a1a1a] flex items-center justify-between">
                            <span className="text-xs font-semibold text-[#e5e5e5]">New Booking</span>
                            <button onClick={() => setShowForm(false)} aria-label="Close form"><X className="w-4 h-4 text-[#525252]" /></button>
                        </div>
                        <div className="p-4 grid grid-cols-2 sm:grid-cols-3 gap-3">
                            <input placeholder="Customer name" value={customerName} onChange={(e) => setCustomerName(e.target.value)}
                                className="col-span-2 sm:col-span-1 bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[var(--accent)]/50 focus:outline-none" />
                            <input placeholder="Phone" value={customerPhone} onChange={(e) => setCustomerPhone(e.target.value)}
                                className="bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[var(--accent)]/50 focus:outline-none" />
                            <input placeholder="Party size" value={partySize} onChange={(e) => setPartySize(e.target.value)} type="number"
                                className="bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[var(--accent)]/50 focus:outline-none" />
                            <input value={reservationDate} onChange={(e) => setReservationDate(e.target.value)} type="date"
                                className="bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] focus:border-[var(--accent)]/50 focus:outline-none" />
                            <input value={reservationTime} onChange={(e) => setReservationTime(e.target.value)} type="time"
                                className="bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] focus:border-[var(--accent)]/50 focus:outline-none" />
                            <input placeholder="Notes" value={notes} onChange={(e) => setNotes(e.target.value)}
                                className="col-span-2 bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[var(--accent)]/50 focus:outline-none" />
                            <button onClick={handleCreate} disabled={!customerName || !reservationDate || !reservationTime || submitting}
                                className="bg-[var(--accent)] text-black rounded-lg px-4 py-2 text-xs font-semibold disabled:opacity-50">
                                {submitting ? "Booking..." : "Book"}
                            </button>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Today at a glance */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="bg-[#141414] border border-[#262626] rounded-xl p-4">
                    <p className="text-xs text-[#525252]">Today</p>
                    <p className="text-lg font-bold text-[var(--accent)] mt-1">{todayBookings.length}</p>
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

                        {overbooking.recommended_rate > 0 && (
                            <div className="bg-[var(--accent)]/5 border border-[var(--accent)]/10 rounded-lg px-3 py-2">
                                <p className="text-xs text-[#e5e5e5] flex items-center gap-2">
                                    <DollarSign className="w-3 h-3 text-[var(--accent)]" />
                                    You can safely take <span className="font-bold text-[var(--accent)]">{overbooking.recommended_rate}% more bookings</span> to make up for no-shows — that&apos;s about <span className="font-bold text-[var(--accent)]">{formatKES(overbooking.potential_monthly_recovery || 0)} extra per month</span>
                                </p>
                            </div>
                        )}

                        {recommendations.length > 0 && (
                            <div className="space-y-1.5 pt-2 border-t border-[#1a1a1a]">
                                <p className="text-[10px] text-[#525252] uppercase tracking-wider">Suggestions</p>
                                {recommendations.slice(0, 3).map((rec: any, i: number) => (
                                    <div key={i} className="flex items-start gap-2 text-xs">
                                        <span className="text-[var(--accent)] mt-0.5">💡</span>
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
                        <p className="text-sm text-[#525252]">No bookings yet — use New Booking to add one</p>
                    </div>
                ) : (
                    <>
                        <div className="px-4 py-3 border-b border-[#1a1a1a]">
                            <h2 className="text-sm font-semibold text-[#e5e5e5]">All Bookings</h2>
                        </div>
                        <div className="divide-y divide-[#1a1a1a]">
                            {reservations.map((res, i) => (
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
                                        <div className="flex items-center gap-1.5 mt-1">
                                            <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${statusStyles[res.status] || statusStyles.confirmed}`}>
                                                {statusLabels[res.status] || res.status}
                                            </span>
                                            {res.status === "confirmed" && (
                                                <>
                                                    <button onClick={() => handleStatusChange(res.id, "completed")} disabled={submitting}
                                                        className="text-[9px] px-1.5 py-0.5 rounded bg-[#1a1a1a] text-[#737373] hover:text-[#22c55e] transition-all">
                                                        Done
                                                    </button>
                                                    <button onClick={() => handleStatusChange(res.id, "no_show")} disabled={submitting}
                                                        className="text-[9px] px-1.5 py-0.5 rounded bg-[#1a1a1a] text-[#737373] hover:text-[#eab308] transition-all">
                                                        No-show
                                                    </button>
                                                    <button onClick={() => handleStatusChange(res.id, "cancelled")} disabled={submitting}
                                                        className="text-[9px] px-1.5 py-0.5 rounded bg-[#1a1a1a] text-[#737373] hover:text-[#ef4444] transition-all">
                                                        Cancel
                                                    </button>
                                                </>
                                            )}
                                        </div>
                                    </div>
                                </motion.div>
                            ))}
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
