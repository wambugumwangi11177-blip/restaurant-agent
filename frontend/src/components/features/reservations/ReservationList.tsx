"use client";

import { AnimatePresence, motion } from "framer-motion";
import { CalendarDays, DollarSign, Pencil } from "lucide-react";
import FormField from "@/components/ui/FormField";
import type { Reservation, FloorTable, ReservationAiData } from "./types";

export interface EditForm {
    party_size: string;
    reservation_date: string;
    reservation_time: string;
    notes: string;
    table_id: string;
}

interface ReservationListProps {
    reservations: Reservation[];
    floorTables: FloorTable[];
    aiData: ReservationAiData | null;
    submitting: boolean;
    editingId: number | null;
    editForm: EditForm;
    onEditFormChange: (form: EditForm) => void;
    editSuggestedTables: FloorTable[] | null;
    onOpenEdit: (res: Reservation) => void;
    onCancelEdit: () => void;
    onSaveEdit: (id: number) => void;
    onStatusChange: (id: number, status: string) => void;
}

const STATUS_LABELS: Record<string, string> = {
    confirmed: "Confirmed",
    cancelled: "Cancelled",
    completed: "Done",
    no_show: "Didn't show",
};
const STATUS_STYLES: Record<string, string> = {
    confirmed: "bg-success/10 text-success",
    cancelled: "bg-danger/10 text-danger",
    completed: "bg-text-muted/10 text-text-muted",
    no_show: "bg-warning/10 text-warning",
};

function formatKES(cents: number) {
    if (!cents) return "KES 0";
    return `KES ${(cents / 100).toLocaleString("en-KE", { maximumFractionDigits: 0 })}`;
}

/**
 * Today-at-a-glance stats, AI insights, and the full bookings list
 * (with inline edit) — extracted from ReservationsWorkspace.
 */
export default function ReservationList({
    reservations,
    floorTables,
    aiData,
    submitting,
    editingId,
    editForm,
    onEditFormChange,
    editSuggestedTables,
    onOpenEdit,
    onCancelEdit,
    onSaveEdit,
    onStatusChange,
}: ReservationListProps) {
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
        <>
            {/* Today at a glance */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="bg-surface border border-border rounded-xl p-4">
                    <p className="text-xs text-text-dim">Today</p>
                    <p className="text-lg font-bold text-accent mt-1">{todayBookings.length}</p>
                </div>
                <div className="bg-surface border border-border rounded-xl p-4">
                    <p className="text-xs text-text-dim">Coming Up</p>
                    <p className="text-lg font-bold text-text mt-1">{upcoming.length}</p>
                </div>
                <div className="bg-surface border border-border rounded-xl p-4">
                    <p className="text-xs text-text-dim">Total</p>
                    <p className="text-lg font-bold text-text-muted mt-1">{reservations.length}</p>
                </div>
            </div>

            {/* What we're seeing about bookings */}
            {((noShow.no_show_rate ?? 0) > 0 || (revenue.estimated_revenue_lost ?? 0) > 0 || recommendations.length > 0) && (
                <div className="bg-surface border border-border rounded-xl">
                    <div className="px-4 py-3 border-b border-surface-hover">
                        <p className="text-xs font-semibold text-text">What we&apos;re noticing</p>
                    </div>
                    <div className="px-4 py-3 space-y-3">
                        <div className="space-y-2">
                            {(noShow.no_show_rate ?? 0) > 0 && (
                                <p className="text-xs text-text-muted">
                                    About <span className="text-danger font-semibold">{noShow.no_show_rate?.toFixed(0)}% of people who book don&apos;t show up</span>
                                </p>
                            )}
                            {(revenue.estimated_revenue_lost ?? 0) > 0 && (
                                <p className="text-xs text-text-muted">
                                    That&apos;s costing you roughly <span className="text-danger font-semibold">{formatKES(revenue.estimated_revenue_lost ?? 0)}</span> in lost sales
                                </p>
                            )}
                            {(tables.avg_utilization ?? 0) > 0 && (
                                <p className="text-xs text-text-muted">
                                    Your tables are being used about <span className="text-text font-semibold">{tables.avg_utilization?.toFixed(0)}% of the time</span>
                                </p>
                            )}
                            {deposit.with_deposit_no_show_rate !== undefined && deposit.without_deposit_no_show_rate !== undefined && (
                                <p className="text-xs text-text-muted">
                                    When you collect a deposit, only <span className="text-success font-semibold">{deposit.with_deposit_no_show_rate?.toFixed(0)}% skip</span> compared to <span className="text-danger font-semibold">{deposit.without_deposit_no_show_rate?.toFixed(0)}% without one</span>
                                </p>
                            )}
                        </div>

                        {(overbooking.recommended_rate ?? 0) > 0 && (
                            <div className="bg-accent/5 border border-accent/10 rounded-lg px-3 py-2">
                                <p className="text-xs text-text flex items-center gap-2">
                                    <DollarSign className="w-3 h-3 text-accent" />
                                    You can safely take <span className="font-bold text-accent">{overbooking.recommended_rate}% more bookings</span> to make up for no-shows — that&apos;s about <span className="font-bold text-accent">{formatKES(overbooking.potential_monthly_recovery || 0)} extra per month</span>
                                </p>
                            </div>
                        )}

                        {recommendations.length > 0 && (
                            <div className="space-y-1.5 pt-2 border-t border-surface-hover">
                                <p className="text-[10px] text-text-dim uppercase tracking-wider">Suggestions</p>
                                {recommendations.slice(0, 3).map((rec, i: number) => (
                                    <div key={i} className="flex items-start gap-2 text-xs">
                                        <span className="text-accent mt-0.5">💡</span>
                                        <div>
                                            <p className="text-text">{rec.message}</p>
                                            {rec.action && <p className="text-text-dim mt-0.5">{rec.action}</p>}
                                            {rec.estimated_impact && (
                                                <p className="text-[10px] text-success mt-0.5">Could save you {rec.estimated_impact}</p>
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
            <div className="bg-surface border border-border rounded-xl">
                {reservations.length === 0 ? (
                    <div className="px-5 py-10 text-center">
                        <CalendarDays className="w-8 h-8 text-[#333] mx-auto mb-3" />
                        <p className="text-sm text-text-dim">No bookings yet — use New Booking to add one</p>
                    </div>
                ) : (
                    <>
                        <div className="px-4 py-3 border-b border-surface-hover">
                            <h2 className="text-sm font-semibold text-text">All Bookings</h2>
                        </div>
                        <div className="divide-y divide-surface-hover">
                            {reservations.map((res, i) => (
                                <motion.div key={res.id || i} initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                                    transition={{ delay: i * 0.03 }}
                                    className="px-4 py-3 hover:bg-surface-hover transition-colors">
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <p className="text-sm text-text">{res.customer_name}</p>
                                            <p className="text-xs text-text-dim mt-0.5">
                                                {res.party_size} guest{res.party_size !== 1 ? "s" : ""}{res.customer_phone && ` · ${res.customer_phone}`}
                                                {res.table_id && ` · Table ${floorTables.find((t) => t.id === res.table_id)?.table_number ?? res.table_id}`}
                                            </p>
                                        </div>
                                        <div className="text-right">
                                            <p className="text-sm text-text-muted">{res.reservation_date}</p>
                                            <p className="text-xs text-text-dim mt-0.5">{res.reservation_time}</p>
                                            <div className="flex items-center gap-1.5 mt-1">
                                                <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${STATUS_STYLES[res.status] || STATUS_STYLES.confirmed}`}>
                                                    {STATUS_LABELS[res.status] || res.status}
                                                </span>
                                                {res.status === "confirmed" && (
                                                    <>
                                                        <button onClick={() => onOpenEdit(res)} disabled={submitting}
                                                            className="text-[9px] px-1.5 py-0.5 rounded bg-surface-hover text-text-muted hover:text-accent transition-all flex items-center gap-0.5">
                                                            <Pencil className="w-2.5 h-2.5" />
                                                            Edit
                                                        </button>
                                                        <button onClick={() => onStatusChange(res.id, "completed")} disabled={submitting}
                                                            className="text-[9px] px-1.5 py-0.5 rounded bg-surface-hover text-text-muted hover:text-success transition-all">
                                                            Done
                                                        </button>
                                                        <button onClick={() => onStatusChange(res.id, "no_show")} disabled={submitting}
                                                            className="text-[9px] px-1.5 py-0.5 rounded bg-surface-hover text-text-muted hover:text-warning transition-all">
                                                            No-show
                                                        </button>
                                                        <button onClick={() => onStatusChange(res.id, "cancelled")} disabled={submitting}
                                                            className="text-[9px] px-1.5 py-0.5 rounded bg-surface-hover text-text-muted hover:text-danger transition-all">
                                                            Cancel
                                                        </button>
                                                    </>
                                                )}
                                            </div>
                                        </div>
                                    </div>

                                    <AnimatePresence>
                                        {editingId === res.id && (
                                            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                                className="mt-2 grid grid-cols-2 sm:grid-cols-5 gap-2 overflow-hidden">
                                                <FormField
                                                    label="Party size"
                                                    srOnlyLabel
                                                    placeholder="Party size"
                                                    value={editForm.party_size}
                                                    type="number"
                                                    onChange={(e) => onEditFormChange({ ...editForm, party_size: e.target.value })}
                                                    className="bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none"
                                                />
                                                <FormField
                                                    label="Reservation date"
                                                    srOnlyLabel
                                                    value={editForm.reservation_date}
                                                    type="date"
                                                    onChange={(e) => onEditFormChange({ ...editForm, reservation_date: e.target.value })}
                                                    className="bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text focus:outline-none"
                                                />
                                                <FormField
                                                    label="Reservation time"
                                                    srOnlyLabel
                                                    value={editForm.reservation_time}
                                                    type="time"
                                                    onChange={(e) => onEditFormChange({ ...editForm, reservation_time: e.target.value })}
                                                    className="bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text focus:outline-none"
                                                />
                                                <div className="flex flex-col gap-1">
                                                    <label htmlFor={`edit-table-${res.id}`} className="sr-only">Table</label>
                                                    <select id={`edit-table-${res.id}`} value={editForm.table_id} onChange={(e) => onEditFormChange({ ...editForm, table_id: e.target.value })}
                                                        className="bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text focus:outline-none">
                                                        <option value="">No table</option>
                                                        {editSuggestedTables !== null ? (
                                                            <>
                                                                <optgroup label="Suggested">
                                                                    {editSuggestedTables.map((t) => <option key={t.table_id} value={t.table_id}>Table {t.table_number}</option>)}
                                                                </optgroup>
                                                                {floorTables.filter((t) => !editSuggestedTables.some((s) => s.table_id === t.id)).length > 0 && (
                                                                    <optgroup label="Other">
                                                                        {floorTables.filter((t) => !editSuggestedTables.some((s) => s.table_id === t.id))
                                                                            .map((t) => <option key={t.id} value={t.id}>Table {t.table_number}</option>)}
                                                                    </optgroup>
                                                                )}
                                                            </>
                                                        ) : (
                                                            floorTables.map((t) => <option key={t.id} value={t.id}>Table {t.table_number}</option>)
                                                        )}
                                                    </select>
                                                </div>
                                                <FormField
                                                    label="Notes"
                                                    srOnlyLabel
                                                    placeholder="Notes"
                                                    value={editForm.notes}
                                                    onChange={(e) => onEditFormChange({ ...editForm, notes: e.target.value })}
                                                    className="bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none"
                                                />
                                                <div className="col-span-2 sm:col-span-5 flex justify-end gap-2">
                                                    <button onClick={onCancelEdit}
                                                        className="text-xs px-3 py-1.5 rounded-lg text-text-muted hover:text-text transition-colors">
                                                        Cancel
                                                    </button>
                                                    <button onClick={() => onSaveEdit(res.id)} disabled={submitting}
                                                        className="bg-accent text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                                                        {submitting ? "Saving..." : "Save"}
                                                    </button>
                                                </div>
                                            </motion.div>
                                        )}
                                    </AnimatePresence>
                                </motion.div>
                            ))}
                        </div>
                    </>
                )}
            </div>
        </>
    );
}
