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
} from "lucide-react";

interface OrderItem {
    id: number;
    menu_item_id: number;
    quantity: number;
    unit_price: number;
    item_name: string;
}

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

export default function KitchenPage() {
    const [orders, setOrders] = useState<Order[]>([]);
    const [loading, setLoading] = useState(true);
    const [updating, setUpdating] = useState<number | null>(null);

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

    const pending = orders.filter((o) => o.status === "pending");
    const cooking = orders.filter((o) => o.status === "prep");
    const ready = orders.filter((o) => o.status === "ready");

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
                <button
                    onClick={fetchOrders}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-[#1a1a1a] border border-[#262626] rounded-lg text-xs text-[#737373] hover:text-[#e5e5e5] transition-all"
                >
                    <RefreshCw className="w-3 h-3" />
                    Refresh
                </button>
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
                    updating={updating}
                    minutesAgo={minutesAgo}
                    orderTypeIcon={orderTypeIcon}
                    channelLabel={channelLabel}
                />
            </div>
        </div>
    );
}

function Column({
    title, subtitle, count, color, icon: Icon, orders, actionLabel, actionStatus,
    onAction, updating, minutesAgo, orderTypeIcon, channelLabel,
}: {
    title: string; subtitle: string; count: number; color: string;
    icon: any; orders: Order[]; actionLabel: string; actionStatus: string;
    onAction: (id: number, status: string) => void;
    updating: number | null;
    minutesAgo: (d: string) => string;
    orderTypeIcon: (t: string) => any;
    channelLabel: (c: string) => string;
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
                                                <span className="text-xs font-semibold text-[#d4a853] w-4">{item.quantity}×</span>
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
                                </motion.div>
                            );
                        })
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
}
