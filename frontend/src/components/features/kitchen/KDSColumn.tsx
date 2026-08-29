"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
    Clock,
    ArrowRight,
    XCircle,
    StickyNote,
    RotateCcw,
    AlertOctagon,
    type LucideIcon,
} from "lucide-react";
import FormField from "@/components/ui/FormField";
import type { Order } from "./KDSBoard";

/**
 * A single status column (Incoming / Cooking / Ready) on the kitchen
 * display board. Extracted from `KDSBoard.tsx` so the board composer stays
 * focused on data-fetching/orchestration.
 */
export default function KDSColumn({
    title, subtitle, count, color, icon: Icon, orders, actionLabel, actionStatus,
    onAction, updating, minutesAgo, orderTypeIcon, channelLabel, readOnly, now,
    allowReject = false, rejectingId = null, setRejectingId, rejectReason = "", setRejectReason, onReject,
    notingId = null, setNotingId, noteText = "", setNoteText, onAddNote,
    incidentId = null, setIncidentId, incidentType = "remake", setIncidentType,
    incidentReason = "", setIncidentReason, onLogIncident,
}: {
    title: string; subtitle: string; count: number; color: string;
    icon: LucideIcon; orders: Order[]; actionLabel: string; actionStatus: string;
    onAction: (id: number, status: string) => void;
    updating: number | null;
    minutesAgo: (d: string) => string;
    orderTypeIcon: (t: string) => LucideIcon;
    channelLabel: (c: string) => string;
    readOnly: boolean;
    now: number;
    allowReject?: boolean;
    rejectingId?: number | null;
    setRejectingId?: (id: number | null) => void;
    rejectReason?: string;
    setRejectReason?: (s: string) => void;
    onReject?: (id: number) => void;
    notingId?: number | null;
    setNotingId?: (id: number | null) => void;
    noteText?: string;
    setNoteText?: (s: string) => void;
    onAddNote?: (id: number) => void;
    incidentId?: number | null;
    setIncidentId?: (id: number | null) => void;
    incidentType?: "remake" | "quality_issue";
    setIncidentType?: (t: "remake" | "quality_issue") => void;
    incidentReason?: string;
    setIncidentReason?: (s: string) => void;
    onLogIncident?: (id: number) => void;
}) {
    return (
        <div className="bg-[#0f0f0f] border border-border rounded-xl flex flex-col min-h-0">
            <div className="px-4 py-3 border-b border-surface-hover flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Icon className="w-4 h-4" style={{ color }} />
                    <div>
                        <span className="text-sm font-semibold text-text">{title}</span>
                        <span className="text-[10px] text-text-dim ml-2">{subtitle}</span>
                    </div>
                </div>
                {count > 0 && (
                    <span className="text-xs font-bold px-2 py-0.5 rounded-full"
                        style={{ backgroundColor: `${color}15`, color }}>
                        {count}
                    </span>
                )}
            </div>

            <div className="flex-1 overflow-y-auto p-2 space-y-2">
                <AnimatePresence>
                    {orders.length === 0 ? (
                        <p className="text-xs text-text-dim text-center py-8">Nothing here</p>
                    ) : (
                        orders.map((order) => {
                            const TypeIcon = orderTypeIcon(order.order_type);
                            const channel = channelLabel(order.delivery_channel);
                            const isOld = now - new Date(order.created_at).getTime() > 15 * 60000;

                            return (
                                <motion.div
                                    key={order.id}
                                    layout
                                    initial={{ opacity: 0, scale: 0.95 }}
                                    animate={{ opacity: 1, scale: 1 }}
                                    exit={{ opacity: 0, scale: 0.95 }}
                                    className={`bg-surface border rounded-xl p-3 ${isOld ? "border-danger/30" : "border-border"
                                        }`}
                                >
                                    {/* Order header */}
                                    <div className="flex items-center justify-between mb-2">
                                        <div className="flex items-center gap-2">
                                            <span className="text-xs font-bold text-text">#{order.id}</span>
                                            <TypeIcon className="w-3 h-3 text-text-dim" />
                                            {order.table_number && (
                                                <span className="text-[10px] text-text-muted">Table {order.table_number}</span>
                                            )}
                                            {channel && (
                                                <span className="text-[9px] px-1.5 py-0.5 rounded bg-info/10 text-info">{channel}</span>
                                            )}
                                        </div>
                                        <span className={`text-[10px] ${isOld ? "text-danger" : "text-text-dim"}`}>
                                            <Clock className="w-2.5 h-2.5 inline mr-0.5" />
                                            {minutesAgo(order.created_at)}
                                        </span>
                                    </div>

                                    {/* Customer */}
                                    {order.customer_name && (
                                        <p className="text-[10px] text-text-muted mb-1.5">{order.customer_name}</p>
                                    )}

                                    {/* Items */}
                                    <div className="space-y-0.5 mb-2">
                                        {order.items.map((item) => (
                                            <div key={item.id} className="flex items-center gap-2">
                                                <span className="text-xs font-semibold text-accent w-4">{item.quantity}×</span>
                                                <span className="text-xs text-text">{item.item_name || `Item #${item.menu_item_id}`}</span>
                                            </div>
                                        ))}
                                    </div>

                                    {/* Notes */}
                                    {order.notes && (
                                        <p className="text-[10px] text-warning bg-warning/5 rounded px-2 py-1 mb-2">
                                            📝 {order.notes}
                                        </p>
                                    )}

                                    {/* Action button */}
                                    {!readOnly && (
                                        <button
                                            onClick={() => onAction(order.id, actionStatus)}
                                            disabled={updating === order.id}
                                            className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-semibold transition-all"
                                            style={{
                                                backgroundColor: `${color}15`,
                                                color,
                                            }}
                                        >
                                            {updating === order.id ? "Updating..." : (
                                                <>
                                                    {actionLabel}
                                                    <ArrowRight className="w-3 h-3" />
                                                </>
                                            )}
                                        </button>
                                    )}

                                    {/* Reject (Incoming column only) + Add note */}
                                    {!readOnly && (allowReject || onAddNote) && (
                                        <div className="flex gap-1.5 mt-1.5">
                                            {allowReject && (
                                                <button
                                                    onClick={() => { setRejectingId?.(rejectingId === order.id ? null : order.id); setNotingId?.(null); }}
                                                    disabled={updating === order.id}
                                                    className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[10px] font-medium bg-danger/10 text-danger hover:bg-danger/20 transition-all">
                                                    <XCircle className="w-3 h-3" />
                                                    Reject
                                                </button>
                                            )}
                                            {onAddNote && (
                                                <button
                                                    onClick={() => { setNotingId?.(notingId === order.id ? null : order.id); setRejectingId?.(null); setIncidentId?.(null); }}
                                                    disabled={updating === order.id}
                                                    className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[10px] font-medium bg-surface-hover text-text-muted hover:text-text transition-all">
                                                    <StickyNote className="w-3 h-3" />
                                                    Note
                                                </button>
                                            )}
                                        </div>
                                    )}

                                    {/* Remake / quality issue */}
                                    {!readOnly && onLogIncident && (
                                        <div className="flex gap-1.5 mt-1.5">
                                            <button
                                                onClick={() => { setIncidentId?.(incidentId === order.id ? null : order.id); setIncidentType?.("remake"); setRejectingId?.(null); setNotingId?.(null); }}
                                                disabled={updating === order.id}
                                                className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[10px] font-medium bg-surface-hover text-text-muted hover:text-accent transition-all">
                                                <RotateCcw className="w-3 h-3" />
                                                Remake
                                            </button>
                                            <button
                                                onClick={() => { setIncidentId?.(incidentId === order.id ? null : order.id); setIncidentType?.("quality_issue"); setRejectingId?.(null); setNotingId?.(null); }}
                                                disabled={updating === order.id}
                                                className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[10px] font-medium bg-surface-hover text-text-muted hover:text-warning transition-all">
                                                <AlertOctagon className="w-3 h-3" />
                                                Issue
                                            </button>
                                        </div>
                                    )}

                                    {incidentId === order.id && (
                                        <div className="mt-1.5 flex gap-1.5 items-center">
                                            <FormField
                                                label={incidentType === "remake" ? "Why is it being remade?" : "What happened?"}
                                                srOnlyLabel
                                                placeholder={incidentType === "remake" ? "Why is it being remade?" : "What happened?"}
                                                value={incidentReason}
                                                onChange={(e) => setIncidentReason?.(e.target.value)}
                                                className="flex-1 bg-surface-hover border border-border rounded-lg px-2 py-1 text-[10px] text-text placeholder-text-dim focus:outline-none" />
                                            <button onClick={() => onLogIncident?.(order.id)} disabled={updating === order.id}
                                                className="bg-accent text-black rounded-lg px-2 py-1 text-[10px] font-semibold disabled:opacity-50">
                                                Log
                                            </button>
                                        </div>
                                    )}

                                    {rejectingId === order.id && (
                                        <div className="mt-1.5 flex gap-1.5 items-center">
                                            <FormField
                                                label="Rejection reason (optional)"
                                                srOnlyLabel
                                                placeholder="Reason (optional)"
                                                value={rejectReason}
                                                onChange={(e) => setRejectReason?.(e.target.value)}
                                                className="flex-1 bg-surface-hover border border-border rounded-lg px-2 py-1 text-[10px] text-text placeholder-text-dim focus:outline-none" />
                                            <button onClick={() => onReject?.(order.id)} disabled={updating === order.id}
                                                className="bg-danger text-white rounded-lg px-2 py-1 text-[10px] font-semibold disabled:opacity-50">
                                                Confirm
                                            </button>
                                        </div>
                                    )}

                                    {notingId === order.id && (
                                        <div className="mt-1.5 flex gap-1.5 items-center">
                                            <FormField
                                                label="Note for this order"
                                                srOnlyLabel
                                                placeholder="Note for this order"
                                                value={noteText}
                                                onChange={(e) => setNoteText?.(e.target.value)}
                                                className="flex-1 bg-surface-hover border border-border rounded-lg px-2 py-1 text-[10px] text-text placeholder-text-dim focus:outline-none" />
                                            <button onClick={() => onAddNote?.(order.id)} disabled={updating === order.id || !noteText.trim()}
                                                className="bg-accent text-black rounded-lg px-2 py-1 text-[10px] font-semibold disabled:opacity-50">
                                                Add
                                            </button>
                                        </div>
                                    )}
                                </motion.div>
                            );
                        })
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
}
