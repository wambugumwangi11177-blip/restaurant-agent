"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import api from "@/lib/api";
import { formatKES } from "@/lib/format";
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
    Maximize2,
    Minimize2,
    RotateCcw,
    CheckSquare,
    Square,
    Flame,
    Coffee,
    Salad,
    Layers,
    Volume2,
    VolumeX,
} from "lucide-react";

interface ModifierItem {
    id?: number;
    name: string;
    price_delta_cents?: number;
}

interface OrderItem {
    id: number;
    menu_item_id: number;
    quantity: number;
    unit_price: number;
    item_name: string;
    notes?: string;
    modifiers?: ModifierItem[];
    is_voided?: boolean;
}

interface Order {
    id: number;
    status: "pending" | "prep" | "ready" | "served" | "cancelled";
    order_type: string;
    delivery_channel: string;
    customer_name: string;
    customer_phone: string;
    table_number: number | null;
    total: number;
    notes: string;
    created_at: string;
    completed_at?: string;
    items: OrderItem[];
    attributed_user_id?: number;
}

export default function KitchenPage() {
    const [orders, setOrders] = useState<Order[]>([]);
    const [loading, setLoading] = useState(true);
    const [updating, setUpdating] = useState<number | null>(null);
    const [stationFilter, setStationFilter] = useState("all");
    const [isFullBleed, setIsFullBleed] = useState(false);
    const [soundEnabled, setSoundEnabled] = useState(true);
    const [completedHistory, setCompletedHistory] = useState<Order[]>([]);
    const [showHistoryModal, setShowHistoryModal] = useState(false);

    // Track checked/bumped item IDs locally per order
    const [bumpedItemIds, setBumpedItemIds] = useState<Record<number, boolean>>({});

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
        const interval = setInterval(fetchOrders, 5000); // 5s refresh
        return () => clearInterval(interval);
    }, [fetchOrders]);

    const moveOrder = async (orderId: number, newStatus: string) => {
        setUpdating(orderId);
        try {
            const targetOrder = orders.find((o) => o.id === orderId);
            if (newStatus === "served" && targetOrder) {
                setCompletedHistory((prev) => [targetOrder, ...prev.slice(0, 19)]);
            }
            await api.patch(`/orders/${orderId}/status`, { status: newStatus });
            await fetchOrders();
        } catch (err) {
            console.error("Failed to update order:", err);
        }
        setUpdating(null);
    };

    const recallOrder = async (orderId: number) => {
        try {
            await api.patch(`/orders/${orderId}/status`, { status: "ready" });
            setCompletedHistory((prev) => prev.filter((o) => o.id !== orderId));
            await fetchOrders();
        } catch {}
    };

    const toggleItemBump = (itemId: number) => {
        setBumpedItemIds((prev) => ({ ...prev, [itemId]: !prev[itemId] }));
    };

    // Calculate minutes waiting
    const getAgeMinutes = (dateStr: string) => {
        const diff = Date.now() - new Date(dateStr).getTime();
        return Math.floor(diff / 60000);
    };

    const getAgeBadge = (dateStr: string) => {
        const mins = getAgeMinutes(dateStr);
        if (mins < 1) return { text: "<1m", color: "bg-emerald-950/80 border-emerald-800 text-emerald-400" };
        if (mins < 8) return { text: `${mins}m`, color: "bg-emerald-950/80 border-emerald-800 text-emerald-400" };
        if (mins < 15) return { text: `${mins}m`, color: "bg-amber-950/80 border-amber-800 text-amber-300 animate-pulse" };
        return { text: `${mins}m`, color: "bg-red-950/90 border-red-800 text-red-300 font-bold animate-bounce" };
    };

    const stations = ["all", "grill", "fryer", "salad", "drinks", "main"];

    const pending = useMemo(() => orders.filter((o) => o.status === "pending"), [orders]);
    const cooking = useMemo(() => orders.filter((o) => o.status === "prep"), [orders]);
    const ready = useMemo(() => orders.filter((o) => o.status === "ready"), [orders]);

    return (
        <div
            className={`flex flex-col bg-stone-950 text-stone-100 transition-all ${
                isFullBleed ? "fixed inset-0 z-50 p-4" : "h-[calc(100vh-4rem)] p-4 overflow-hidden"
            }`}
        >
            {/* KDS Header & Utility Controls */}
            <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-stone-800/80">
                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2">
                        <ChefHat className="w-6 h-6 text-amber-400" />
                        <h1 className="text-lg font-bold tracking-tight">KDS Kitchen Display</h1>
                    </div>
                    <span className="text-xs bg-stone-900 border border-stone-800 px-2.5 py-1 rounded-full text-stone-400 font-medium">
                        {orders.length} live ticket{orders.length === 1 ? "" : "s"}
                    </span>
                </div>

                {/* Stations Filter Tabs */}
                <div className="flex items-center gap-1 bg-stone-900/90 border border-stone-800 p-1 rounded-xl">
                    {stations.map((st) => (
                        <button
                            key={st}
                            onClick={() => setStationFilter(st)}
                            className={`px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wider transition-all ${
                                stationFilter === st
                                    ? "bg-amber-500 text-stone-950 shadow"
                                    : "text-stone-400 hover:text-stone-200"
                            }`}
                        >
                            {st}
                        </button>
                    ))}
                </div>

                {/* Action Controls: Recall, Audio, Full-Bleed */}
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => setShowHistoryModal(true)}
                        className="px-3 py-1.5 rounded-lg bg-stone-900 border border-stone-800 text-xs font-medium text-stone-300 hover:bg-stone-800 flex items-center gap-1.5"
                    >
                        <RotateCcw className="w-3.5 h-3.5 text-amber-400" />
                        Recall ({completedHistory.length})
                    </button>
                    <button
                        onClick={() => setSoundEnabled(!soundEnabled)}
                        className="p-2 rounded-lg bg-stone-900 border border-stone-800 text-stone-400 hover:text-stone-200"
                        title={soundEnabled ? "Sound enabled" : "Sound muted"}
                    >
                        {soundEnabled ? <Volume2 className="w-4 h-4 text-emerald-400" /> : <VolumeX className="w-4 h-4 text-stone-500" />}
                    </button>
                    <button
                        onClick={() => setIsFullBleed(!isFullBleed)}
                        className="p-2 rounded-lg bg-stone-900 border border-stone-800 text-stone-400 hover:text-stone-200"
                        title={isFullBleed ? "Exit Fullscreen" : "Fullscreen Kitchen Board"}
                    >
                        {isFullBleed ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                    </button>
                </div>
            </div>

            {/* Kanban Column Grid */}
            <div className="flex-1 grid grid-cols-1 md:grid-cols-3 gap-4 pt-3 overflow-hidden">
                {/* COLUMN 1: Incoming / Pending */}
                <div className="flex flex-col bg-stone-900/50 rounded-2xl border border-stone-800/80 overflow-hidden">
                    <div className="p-3 bg-stone-900/90 border-b border-stone-800 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <span className="w-2.5 h-2.5 rounded-full bg-blue-500" />
                            <h2 className="text-xs font-bold uppercase tracking-wider text-stone-300">Incoming</h2>
                        </div>
                        <span className="text-xs font-bold text-blue-400 bg-blue-950/60 px-2 py-0.5 rounded-full border border-blue-900/50">
                            {pending.length}
                        </span>
                    </div>
                    <div className="flex-1 p-2.5 overflow-y-auto space-y-2.5">
                        {pending.length === 0 ? (
                            <div className="h-full flex items-center justify-center text-center p-6 text-stone-500 text-xs">
                                No incoming tickets
                            </div>
                        ) : (
                            pending.map((order) => (
                                <TicketCard
                                    key={order.id}
                                    order={order}
                                    ageBadge={getAgeBadge(order.created_at)}
                                    bumpedItemIds={bumpedItemIds}
                                    onToggleItemBump={toggleItemBump}
                                    onBump={() => moveOrder(order.id, "prep")}
                                    actionLabel="Start Cooking"
                                    actionColor="bg-blue-600 hover:bg-blue-500 text-white"
                                    updating={updating === order.id}
                                />
                            ))
                        )}
                    </div>
                </div>

                {/* COLUMN 2: Cooking / Prep */}
                <div className="flex flex-col bg-stone-900/50 rounded-2xl border border-stone-800/80 overflow-hidden">
                    <div className="p-3 bg-stone-900/90 border-b border-stone-800 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <span className="w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse" />
                            <h2 className="text-xs font-bold uppercase tracking-wider text-stone-300">In Prep</h2>
                        </div>
                        <span className="text-xs font-bold text-amber-400 bg-amber-950/60 px-2 py-0.5 rounded-full border border-amber-900/50">
                            {cooking.length}
                        </span>
                    </div>
                    <div className="flex-1 p-2.5 overflow-y-auto space-y-2.5">
                        {cooking.length === 0 ? (
                            <div className="h-full flex items-center justify-center text-center p-6 text-stone-500 text-xs">
                                Kitchen clear
                            </div>
                        ) : (
                            cooking.map((order) => (
                                <TicketCard
                                    key={order.id}
                                    order={order}
                                    ageBadge={getAgeBadge(order.created_at)}
                                    bumpedItemIds={bumpedItemIds}
                                    onToggleItemBump={toggleItemBump}
                                    onBump={() => moveOrder(order.id, "ready")}
                                    actionLabel="Mark Ready"
                                    actionColor="bg-amber-500 hover:bg-amber-400 text-stone-950"
                                    updating={updating === order.id}
                                />
                            ))
                        )}
                    </div>
                </div>

                {/* COLUMN 3: Ready / Expo */}
                <div className="flex flex-col bg-stone-900/50 rounded-2xl border border-stone-800/80 overflow-hidden">
                    <div className="p-3 bg-stone-900/90 border-b border-stone-800 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                            <h2 className="text-xs font-bold uppercase tracking-wider text-stone-300">Ready to Serve</h2>
                        </div>
                        <span className="text-xs font-bold text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded-full border border-emerald-900/50">
                            {ready.length}
                        </span>
                    </div>
                    <div className="flex-1 p-2.5 overflow-y-auto space-y-2.5">
                        {ready.length === 0 ? (
                            <div className="h-full flex items-center justify-center text-center p-6 text-stone-500 text-xs">
                                No orders ready
                            </div>
                        ) : (
                            ready.map((order) => (
                                <TicketCard
                                    key={order.id}
                                    order={order}
                                    ageBadge={getAgeBadge(order.created_at)}
                                    bumpedItemIds={bumpedItemIds}
                                    onToggleItemBump={toggleItemBump}
                                    onBump={() => moveOrder(order.id, "served")}
                                    actionLabel="Expo / Served"
                                    actionColor="bg-emerald-500 hover:bg-emerald-400 text-stone-950"
                                    updating={updating === order.id}
                                />
                            ))
                        )}
                    </div>
                </div>
            </div>

            {/* RECALL MODAL */}
            {showHistoryModal && (
                <div className="fixed inset-0 bg-stone-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-stone-900 border border-stone-800 rounded-2xl max-w-md w-full p-5 flex flex-col gap-4 max-h-[80vh]">
                        <div className="flex items-center justify-between border-b border-stone-800 pb-3">
                            <h3 className="text-sm font-bold text-stone-100">Recently Served Tickets</h3>
                            <button onClick={() => setShowHistoryModal(false)} className="text-stone-400 hover:text-stone-200">
                                &times;
                            </button>
                        </div>
                        <div className="flex-1 overflow-y-auto space-y-2">
                            {completedHistory.length === 0 ? (
                                <p className="text-center text-xs text-stone-500 py-8">No recently completed orders to recall.</p>
                            ) : (
                                completedHistory.map((h) => (
                                    <div
                                        key={h.id}
                                        className="p-3 bg-stone-950 rounded-xl border border-stone-800 flex items-center justify-between"
                                    >
                                        <div>
                                            <span className="text-xs font-bold text-stone-200">
                                                Order #{h.id} {h.table_number ? `(Table ${h.table_number})` : ""}
                                            </span>
                                            <p className="text-[10px] text-stone-400">
                                                {h.items.length} items &bull; {h.customer_name || "Walk-in"}
                                            </p>
                                        </div>
                                        <button
                                            onClick={() => recallOrder(h.id)}
                                            className="px-3 py-1.5 rounded-lg bg-amber-500 text-stone-950 text-xs font-bold hover:bg-amber-400"
                                        >
                                            Restore to Ready
                                        </button>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

function TicketCard({
    order,
    ageBadge,
    bumpedItemIds,
    onToggleItemBump,
    onBump,
    actionLabel,
    actionColor,
    updating,
}: {
    order: Order;
    ageBadge: { text: string; color: string };
    bumpedItemIds: Record<number, boolean>;
    onToggleItemBump: (id: number) => void;
    onBump: () => void;
    actionLabel: string;
    actionColor: string;
    updating: boolean;
}) {
    const channelIcon = (ch: string) => {
        if (ch === "delivery" || ch === "uber_eats" || ch === "glovo" || ch === "bolt_food") return Truck;
        if (ch === "takeout") return ShoppingBag;
        return UtensilsCrossed;
    };
    const Icon = channelIcon(order.delivery_channel || order.order_type);

    return (
        <div className="bg-stone-950/90 border border-stone-800 rounded-xl p-3 flex flex-col gap-2.5 shadow-sm">
            {/* Header: Ticket ID, Table/Customer, Aging Timer */}
            <div className="flex items-start justify-between gap-1 border-b border-stone-800/60 pb-2">
                <div>
                    <div className="flex items-center gap-1.5">
                        <Icon className="w-3.5 h-3.5 text-amber-400" />
                        <span className="text-sm font-bold text-stone-100">
                            #{order.id} {order.table_number ? `&bull; Table ${order.table_number}` : ""}
                        </span>
                    </div>
                    {order.customer_name && (
                        <span className="text-[11px] text-stone-400 block mt-0.5">
                            {order.customer_name}
                        </span>
                    )}
                </div>
                <span className={`text-[11px] font-mono font-bold px-2 py-0.5 rounded border ${ageBadge.color}`}>
                    {ageBadge.text}
                </span>
            </div>

            {/* Line items with checkbox bump */}
            <div className="space-y-1.5">
                {order.items.map((it) => {
                    const isChecked = Boolean(bumpedItemIds[it.id]);
                    return (
                        <div
                            key={it.id}
                            onClick={() => onToggleItemBump(it.id)}
                            className={`p-1.5 rounded-lg flex items-start gap-2 cursor-pointer transition-all ${
                                isChecked ? "bg-stone-900/40 opacity-40 line-through" : "hover:bg-stone-900"
                            }`}
                        >
                            <span className="mt-0.5 text-amber-400">
                                {isChecked ? <CheckSquare className="w-3.5 h-3.5" /> : <Square className="w-3.5 h-3.5" />}
                            </span>
                            <div className="flex-1">
                                <span className="text-xs font-semibold text-stone-200">
                                    {it.quantity}x {it.item_name}
                                </span>
                                {it.modifiers && it.modifiers.length > 0 && (
                                    <p className="text-[10px] text-stone-400">
                                        {it.modifiers.map((m) => `+${m.name}`).join(", ")}
                                    </p>
                                )}
                                {it.notes && (
                                    <p className="text-[10px] text-amber-300/90 italic font-medium">
                                        &bull; {it.notes}
                                    </p>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Order notes */}
            {order.notes && (
                <div className="p-1.5 bg-amber-950/30 border border-amber-900/40 rounded text-[11px] text-amber-300/90 font-medium">
                    Order Note: {order.notes}
                </div>
            )}

            {/* Bump Action Button */}
            <button
                onClick={onBump}
                disabled={updating}
                className={`w-full py-2 rounded-lg font-bold text-xs transition-all flex items-center justify-center gap-1.5 ${actionColor}`}
            >
                {updating ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : actionLabel}
            </button>
        </div>
    );
}
