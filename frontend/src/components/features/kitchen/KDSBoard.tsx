"use client";

import { useEffect, useState, useCallback } from "react";
import api from "@/lib/api";
import { motion, AnimatePresence } from "framer-motion";
import {
    Clock,
    ChefHat,
    CheckCircle2,
    ArrowRight,
    RefreshCw,
    Bell,
    Truck,
    UtensilsCrossed,
    ShoppingBag,
    XCircle,
    StickyNote,
    RotateCcw,
    AlertOctagon,
    LayoutGrid,
} from "lucide-react";

interface OrderItem {
    id: number;
    menu_item_id: number;
    quantity: number;
    unit_price: number;
    item_name: string;
    prep_station: string;
}

const STATIONS = [
    { v: "all", label: "All" },
    { v: "grill", label: "Grill" },
    { v: "fryer", label: "Fryer" },
    { v: "salad", label: "Salad" },
    { v: "drinks", label: "Drinks" },
    { v: "main", label: "Main" },
];

interface Order {
    id: number;
    status: string;
    order_type: string;
    delivery_channel: string;
    customer_name: string;
    table_number: number | null;
    total: number;
    notes: string;
    created_at: string;
    items: OrderItem[];
}

/**
 * The kitchen display board (KDS) — extracted from the original
 * dashboard/kitchen/page.tsx so every tier with `kitchen` access (Owner,
 * Manager, Supervisor, Kitchen RW; Waiter R) can reuse the exact same
 * component. `readOnly` hides the status-advance button — used for Waiter,
 * who can see the board (directive 015: `kitchen` = R for Waiter) but
 * shouldn't be the one moving orders through it.
 */
export default function KDSBoard({ readOnly = false }: { readOnly?: boolean }) {
    const [orders, setOrders] = useState<Order[]>([]);
    const [loading, setLoading] = useState(true);
    const [updating, setUpdating] = useState<number | null>(null);
    const [rejectingId, setRejectingId] = useState<number | null>(null);
    const [rejectReason, setRejectReason] = useState("");
    const [notingId, setNotingId] = useState<number | null>(null);
    const [noteText, setNoteText] = useState("");
    const [stationFilter, setStationFilter] = useState("all");
    const [incidentId, setIncidentId] = useState<number | null>(null);
    const [incidentType, setIncidentType] = useState<"remake" | "quality_issue">("remake");
    const [incidentReason, setIncidentReason] = useState("");

    const fetchOrders = useCallback(async () => {
        try {
            const res = await api.get("/orders/active");
            setOrders(res.data);
        } catch {
            // Silently retry
        }
        setLoading(false);
    }, []);

    useEffect(() => {
        fetchOrders();
        const interval = setInterval(fetchOrders, 10000); // Refresh every 10s
        return () => clearInterval(interval);
    }, [fetchOrders]);

    const moveOrder = async (orderId: number, newStatus: string) => {
        setUpdating(orderId);
        try {
            await api.patch(`/orders/${orderId}/status`, { status: newStatus });
            await fetchOrders();
        } catch (err) {
            console.error("Failed to update order:", err);
        }
        setUpdating(null);
    };

    const rejectOrder = async (orderId: number) => {
        setUpdating(orderId);
        try {
            if (rejectReason.trim()) {
                const order = orders.find((o) => o.id === orderId);
                const note = `Rejected: ${rejectReason.trim()}`;
                await api.patch(`/orders/${orderId}/details`, {
                    notes: order?.notes ? `${order.notes} | ${note}` : note,
                });
            }
            await api.patch(`/orders/${orderId}/status`, { status: "cancelled" });
            setRejectingId(null);
            setRejectReason("");
            await fetchOrders();
        } catch (err) {
            console.error("Failed to reject order:", err);
        }
        setUpdating(null);
    };

    const addNote = async (orderId: number) => {
        if (!noteText.trim()) return;
        setUpdating(orderId);
        try {
            const order = orders.find((o) => o.id === orderId);
            const combined = order?.notes ? `${order.notes} | ${noteText.trim()}` : noteText.trim();
            await api.patch(`/orders/${orderId}/details`, { notes: combined });
            setNotingId(null);
            setNoteText("");
            await fetchOrders();
        } catch (err) {
            console.error("Failed to add note:", err);
        }
        setUpdating(null);
    };

    const logIncident = async (orderId: number) => {
        setUpdating(orderId);
        try {
            await api.post("/orders/incidents", {
                order_id: orderId,
                incident_type: incidentType,
                reason: incidentReason,
            });
            setIncidentId(null);
            setIncidentReason("");
            await fetchOrders();
        } catch (err) {
            console.error("Failed to log incident:", err);
        }
        setUpdating(null);
    };

    // Station filter: an order stays visible if any of its items belong to
    // the selected station; within a visible order, only that station's
    // items are shown (so the grill screen doesn't show drinks). "All"
    // shows every item as before.
    const itemsForStation = (order: Order) =>
        stationFilter === "all" ? order.items : order.items.filter((i) => i.prep_station === stationFilter);
    const matchesStation = (order: Order) => itemsForStation(order).length > 0;

    const filteredOrders = orders.filter(matchesStation).map((o) => ({ ...o, items: itemsForStation(o) }));

    const pending = filteredOrders.filter((o) => o.status === "pending");
    const cooking = filteredOrders.filter((o) => o.status === "prep");
    const ready = filteredOrders.filter((o) => o.status === "ready");

    const minutesAgo = (dateStr: string) => {
        const diff = Date.now() - new Date(dateStr).getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1) return "Just now";
        if (mins === 1) return "1 min ago";
        return `${mins} mins ago`;
    };

    const orderTypeIcon = (type: string) => {
        if (type === "delivery") return Truck;
        if (type === "takeout") return ShoppingBag;
        return UtensilsCrossed;
    };

    const channelLabel = (ch: string) => {
        const map: Record<string, string> = {
            uber_eats: "Uber Eats",
            bolt_food: "Bolt Food",
            glovo: "Glovo",
            walk_in: "",
            app: "App Order",
        };
        return map[ch] || "";
    };

    if (loading) {
        return (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 h-[calc(100vh-120px)]">
                {[...Array(3)].map((_, i) => (
                    <div key={i} className="bg-[#141414] rounded-xl animate-pulse" />
                ))}
            </div>
        );
    }

    return (
        <div className="flex flex-col h-[calc(100vh-120px)]">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h1 className="text-xl font-bold text-[#e5e5e5]">Kitchen</h1>
                    <p className="text-xs text-[#525252]">
                        {orders.length > 0
                            ? `${orders.length} order${orders.length > 1 ? "s" : ""} right now`
                            : "No orders right now — take a breather"}
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <div className="hidden sm:flex items-center gap-1 bg-[#1a1a1a] border border-[#262626] rounded-lg p-0.5">
                        <LayoutGrid className="w-3 h-3 text-[#525252] ml-1.5" />
                        {STATIONS.map((s) => (
                            <button
                                key={s.v}
                                onClick={() => setStationFilter(s.v)}
                                className={`px-2 py-1 rounded text-[10px] font-medium transition-all ${stationFilter === s.v
                                    ? "bg-[var(--accent)] text-black"
                                    : "text-[#737373] hover:text-[#e5e5e5]"
                                    }`}
                            >
                                {s.label}
                            </button>
                        ))}
                    </div>
                    <button
                        onClick={fetchOrders}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-[#1a1a1a] border border-[#262626] rounded-lg text-xs text-[#737373] hover:text-[#e5e5e5] transition-all"
                    >
                        <RefreshCw className="w-3 h-3" />
                        Refresh
                    </button>
                </div>
            </div>

            {/* Three-column board */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 flex-1 min-h-0">
                {/* Incoming */}
                <Column
                    title="Incoming"
                    subtitle="New orders"
                    count={pending.length}
                    color="#eab308"
                    icon={Bell}
                    orders={pending}
                    actionLabel="Start Cooking"
                    actionStatus="prep"
                    onAction={moveOrder}
                    updating={updating}
                    minutesAgo={minutesAgo}
                    orderTypeIcon={orderTypeIcon}
                    channelLabel={channelLabel}
                    readOnly={readOnly}
                    allowReject
                    rejectingId={rejectingId}
                    setRejectingId={setRejectingId}
                    rejectReason={rejectReason}
                    setRejectReason={setRejectReason}
                    onReject={rejectOrder}
                    notingId={notingId}
                    setNotingId={setNotingId}
                    noteText={noteText}
                    setNoteText={setNoteText}
                    onAddNote={addNote}
                    incidentId={incidentId}
                    setIncidentId={setIncidentId}
                    incidentType={incidentType}
                    setIncidentType={setIncidentType}
                    incidentReason={incidentReason}
                    setIncidentReason={setIncidentReason}
                    onLogIncident={logIncident}
                />

                {/* Cooking */}
                <Column
                    title="Cooking"
                    subtitle="Being prepared"
                    count={cooking.length}
                    color="#d4a853"
                    icon={ChefHat}
                    orders={cooking}
                    actionLabel="Ready"
                    actionStatus="ready"
                    onAction={moveOrder}
                    updating={updating}
                    minutesAgo={minutesAgo}
                    orderTypeIcon={orderTypeIcon}
                    channelLabel={channelLabel}
                    readOnly={readOnly}
                    notingId={notingId}
                    setNotingId={setNotingId}
                    noteText={noteText}
                    setNoteText={setNoteText}
                    onAddNote={addNote}
                    incidentId={incidentId}
                    setIncidentId={setIncidentId}
                    incidentType={incidentType}
                    setIncidentType={setIncidentType}
                    incidentReason={incidentReason}
                    setIncidentReason={setIncidentReason}
                    onLogIncident={logIncident}
                />

                {/* Ready */}
                <Column
                    title="Ready"
                    subtitle="Waiting for pickup"
                    count={ready.length}
                    color="#22c55e"
                    icon={CheckCircle2}
                    orders={ready}
                    actionLabel="Served"
                    actionStatus="served"
                    onAction={moveOrder}
                    notingId={notingId}
                    setNotingId={setNotingId}
                    noteText={noteText}
                    setNoteText={setNoteText}
                    onAddNote={addNote}
                    incidentId={incidentId}
                    setIncidentId={setIncidentId}
                    incidentType={incidentType}
                    setIncidentType={setIncidentType}
                    incidentReason={incidentReason}
                    setIncidentReason={setIncidentReason}
                    onLogIncident={logIncident}
                    updating={updating}
                    minutesAgo={minutesAgo}
                    orderTypeIcon={orderTypeIcon}
                    channelLabel={channelLabel}
                    readOnly={readOnly}
                />
            </div>
        </div>
    );
}

function Column({
    title, subtitle, count, color, icon: Icon, orders, actionLabel, actionStatus,
    onAction, updating, minutesAgo, orderTypeIcon, channelLabel, readOnly,
    allowReject = false, rejectingId = null, setRejectingId, rejectReason = "", setRejectReason, onReject,
    notingId = null, setNotingId, noteText = "", setNoteText, onAddNote,
    incidentId = null, setIncidentId, incidentType = "remake", setIncidentType,
    incidentReason = "", setIncidentReason, onLogIncident,
}: {
    title: string; subtitle: string; count: number; color: string;
    icon: any; orders: Order[]; actionLabel: string; actionStatus: string;
    onAction: (id: number, status: string) => void;
    updating: number | null;
    minutesAgo: (d: string) => string;
    orderTypeIcon: (t: string) => any;
    channelLabel: (c: string) => string;
    readOnly: boolean;
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
        <div className="bg-[#0f0f0f] border border-[#262626] rounded-xl flex flex-col min-h-0">
            <div className="px-4 py-3 border-b border-[#1a1a1a] flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Icon className="w-4 h-4" style={{ color }} />
                    <div>
                        <span className="text-sm font-semibold text-[#e5e5e5]">{title}</span>
                        <span className="text-[10px] text-[#525252] ml-2">{subtitle}</span>
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
                        <p className="text-xs text-[#525252] text-center py-8">Nothing here</p>
                    ) : (
                        orders.map((order) => {
                            const TypeIcon = orderTypeIcon(order.order_type);
                            const channel = channelLabel(order.delivery_channel);
                            const isOld = Date.now() - new Date(order.created_at).getTime() > 15 * 60000;

                            return (
                                <motion.div
                                    key={order.id}
                                    layout
                                    initial={{ opacity: 0, scale: 0.95 }}
                                    animate={{ opacity: 1, scale: 1 }}
                                    exit={{ opacity: 0, scale: 0.95 }}
                                    className={`bg-[#141414] border rounded-xl p-3 ${isOld ? "border-[#ef4444]/30" : "border-[#262626]"
                                        }`}
                                >
                                    {/* Order header */}
                                    <div className="flex items-center justify-between mb-2">
                                        <div className="flex items-center gap-2">
                                            <span className="text-xs font-bold text-[#e5e5e5]">#{order.id}</span>
                                            <TypeIcon className="w-3 h-3 text-[#525252]" />
                                            {order.table_number && (
                                                <span className="text-[10px] text-[#737373]">Table {order.table_number}</span>
                                            )}
                                            {channel && (
                                                <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#3b82f6]/10 text-[#3b82f6]">{channel}</span>
                                            )}
                                        </div>
                                        <span className={`text-[10px] ${isOld ? "text-[#ef4444]" : "text-[#525252]"}`}>
                                            <Clock className="w-2.5 h-2.5 inline mr-0.5" />
                                            {minutesAgo(order.created_at)}
                                        </span>
                                    </div>

                                    {/* Customer */}
                                    {order.customer_name && (
                                        <p className="text-[10px] text-[#737373] mb-1.5">{order.customer_name}</p>
                                    )}

                                    {/* Items */}
                                    <div className="space-y-0.5 mb-2">
                                        {order.items.map((item) => (
                                            <div key={item.id} className="flex items-center gap-2">
                                                <span className="text-xs font-semibold text-[var(--accent)] w-4">{item.quantity}×</span>
                                                <span className="text-xs text-[#e5e5e5]">{item.item_name || `Item #${item.menu_item_id}`}</span>
                                            </div>
                                        ))}
                                    </div>

                                    {/* Notes */}
                                    {order.notes && (
                                        <p className="text-[10px] text-[#eab308] bg-[#eab308]/5 rounded px-2 py-1 mb-2">
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
                                                    className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[10px] font-medium bg-[#ef4444]/10 text-[#ef4444] hover:bg-[#ef4444]/20 transition-all">
                                                    <XCircle className="w-3 h-3" />
                                                    Reject
                                                </button>
                                            )}
                                            {onAddNote && (
                                                <button
                                                    onClick={() => { setNotingId?.(notingId === order.id ? null : order.id); setRejectingId?.(null); setIncidentId?.(null); }}
                                                    disabled={updating === order.id}
                                                    className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[10px] font-medium bg-[#1a1a1a] text-[#737373] hover:text-[#e5e5e5] transition-all">
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
                                                className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[10px] font-medium bg-[#1a1a1a] text-[#737373] hover:text-[var(--accent)] transition-all">
                                                <RotateCcw className="w-3 h-3" />
                                                Remake
                                            </button>
                                            <button
                                                onClick={() => { setIncidentId?.(incidentId === order.id ? null : order.id); setIncidentType?.("quality_issue"); setRejectingId?.(null); setNotingId?.(null); }}
                                                disabled={updating === order.id}
                                                className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-[10px] font-medium bg-[#1a1a1a] text-[#737373] hover:text-[#eab308] transition-all">
                                                <AlertOctagon className="w-3 h-3" />
                                                Issue
                                            </button>
                                        </div>
                                    )}

                                    {incidentId === order.id && (
                                        <div className="mt-1.5 flex gap-1.5 items-center">
                                            <input placeholder={incidentType === "remake" ? "Why is it being remade?" : "What happened?"}
                                                value={incidentReason}
                                                onChange={(e) => setIncidentReason?.(e.target.value)}
                                                className="flex-1 bg-[#1a1a1a] border border-[#262626] rounded-lg px-2 py-1 text-[10px] text-[#e5e5e5] placeholder-[#525252] focus:outline-none" />
                                            <button onClick={() => onLogIncident?.(order.id)} disabled={updating === order.id}
                                                className="bg-[var(--accent)] text-black rounded-lg px-2 py-1 text-[10px] font-semibold disabled:opacity-50">
                                                Log
                                            </button>
                                        </div>
                                    )}

                                    {rejectingId === order.id && (
                                        <div className="mt-1.5 flex gap-1.5 items-center">
                                            <input placeholder="Reason (optional)" value={rejectReason}
                                                onChange={(e) => setRejectReason?.(e.target.value)}
                                                className="flex-1 bg-[#1a1a1a] border border-[#262626] rounded-lg px-2 py-1 text-[10px] text-[#e5e5e5] placeholder-[#525252] focus:outline-none" />
                                            <button onClick={() => onReject?.(order.id)} disabled={updating === order.id}
                                                className="bg-[#ef4444] text-white rounded-lg px-2 py-1 text-[10px] font-semibold disabled:opacity-50">
                                                Confirm
                                            </button>
                                        </div>
                                    )}

                                    {notingId === order.id && (
                                        <div className="mt-1.5 flex gap-1.5 items-center">
                                            <input placeholder="Note for this order" value={noteText}
                                                onChange={(e) => setNoteText?.(e.target.value)}
                                                className="flex-1 bg-[#1a1a1a] border border-[#262626] rounded-lg px-2 py-1 text-[10px] text-[#e5e5e5] placeholder-[#525252] focus:outline-none" />
                                            <button onClick={() => onAddNote?.(order.id)} disabled={updating === order.id || !noteText.trim()}
                                                className="bg-[var(--accent)] text-black rounded-lg px-2 py-1 text-[10px] font-semibold disabled:opacity-50">
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
