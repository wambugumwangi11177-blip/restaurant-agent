"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import api from "@/lib/api";
import { formatKES } from "@/lib/format";
import { isOnBusinessDay, nairobiDate } from "@/lib/businessDay";
import { motion, AnimatePresence } from "framer-motion";
import {
    ShoppingBag,
    Search,
    Filter,
    Clock,
    User,
    Phone,
    CreditCard,
    DollarSign,
    UtensilsCrossed,
    CheckCircle2,
    XCircle,
    AlertTriangle,
    RotateCcw,
    Printer,
    Send,
    Receipt,
    History,
    X,
    ChevronRight,
    RefreshCw,
    AlertOctagon,
} from "lucide-react";

interface ModifierOut {
    id: number;
    name: string;
    price_delta_cents: number;
}

interface OrderItemOut {
    id: number;
    menu_item_id: number;
    quantity: number;
    unit_price: number;
    item_name: string;
    is_voided?: boolean;
    void_reason?: string;
    notes?: string;
    modifiers?: ModifierOut[];
}

interface PaymentOut {
    id: number;
    payment_method: string;
    amount_cents: number;
    reference: string;
    created_at: string;
}

interface Order {
    id: number;
    status: "pending" | "prep" | "ready" | "served" | "cancelled";
    order_type: string;
    delivery_channel: string;
    payment_method: string;
    is_paid: boolean;
    customer_name: string;
    customer_phone: string;
    table_number: number | null;
    total: number;
    notes: string;
    discount_cents: number;
    discount_reason: string;
    void_reason: string;
    refund_cents: number;
    refund_reason: string;
    tax_cents: number;
    service_charge_cents: number;
    created_at: string;
    completed_at: string | null;
    items: OrderItemOut[];
    payments: PaymentOut[];
    attributed_user_id?: number | null;
}

export default function OrdersPage() {
    const [orders, setOrders] = useState<Order[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);

    // Filters
    const [statusFilter, setStatusFilter] = useState("all");
    const [channelFilter, setChannelFilter] = useState("all");
    const [unpaidOnly, setUnpaidOnly] = useState(false);
    const [searchQuery, setSearchQuery] = useState("");

    // Modal state for Void / Refund / Take Payment / History
    const [showVoidModal, setShowVoidModal] = useState(false);
    const [voidReason, setVoidReason] = useState("");
    const [voidingTarget, setVoidingTarget] = useState<{ type: "order" | "item"; id: number } | null>(null);

    const [showRefundModal, setShowRefundModal] = useState(false);
    const [refundAmountKES, setRefundAmountKES] = useState<number>(0);
    const [refundReason, setRefundReason] = useState("");

    const [showPayModal, setShowPayModal] = useState(false);
    const [payMethod, setPayMethod] = useState("mpesa");
    const [payReference, setPayReference] = useState("");

    const [customerHistory, setCustomerHistory] = useState<any | null>(null);
    const [historyLoading, setHistoryLoading] = useState(false);

    const fetchOrders = useCallback(async () => {
        try {
            const res = await api.get("/orders/");
            setOrders(Array.isArray(res.data) ? res.data : []);
        } catch {}
        setLoading(false);
    }, []);

    useEffect(() => {
        fetchOrders();
        const interval = setInterval(fetchOrders, 10000);
        return () => clearInterval(interval);
    }, [fetchOrders]);

    const today = nairobiDate();
    const todayOrders = useMemo(() => orders.filter((o) => isOnBusinessDay(o.created_at, today)), [orders, today]);
    const todayRevenue = useMemo(
        () => todayOrders.reduce((s, o) => (o.status !== "cancelled" ? s + (o.total || 0) : s), 0),
        [todayOrders]
    );
    const unpaidCount = useMemo(() => orders.filter((o) => !o.is_paid && o.status !== "cancelled").length, [orders]);
    const avgTicket = todayOrders.length > 0 ? Math.round(todayRevenue / todayOrders.length) : 0;

    // Filtered orders list
    const filteredOrders = useMemo(() => {
        return orders.filter((o) => {
            if (statusFilter !== "all" && o.status !== statusFilter) return false;
            if (channelFilter !== "all" && o.delivery_channel !== channelFilter) return false;
            if (unpaidOnly && o.is_paid) return false;
            if (searchQuery.trim()) {
                const q = searchQuery.toLowerCase();
                const matchesId = o.id.toString().includes(q);
                const matchesName = (o.customer_name || "").toLowerCase().includes(q);
                const matchesPhone = (o.customer_phone || "").toLowerCase().includes(q);
                if (!matchesId && !matchesName && !matchesPhone) return false;
            }
            return true;
        });
    }, [orders, statusFilter, channelFilter, unpaidOnly, searchQuery]);

    // Handle Void
    const handleConfirmVoid = async () => {
        if (!selectedOrder || !voidingTarget || !voidReason.trim()) return;
        try {
            if (voidingTarget.type === "order") {
                const res = await api.post(`/orders/${selectedOrder.id}/void`, { void_reason: voidReason });
                setSelectedOrder(res.data);
            } else {
                const res = await api.post(`/orders/${selectedOrder.id}/items/${voidingTarget.id}/void`, {
                    void_reason: voidReason,
                });
                setSelectedOrder(res.data);
            }
            setShowVoidModal(false);
            setVoidReason("");
            setVoidingTarget(null);
            await fetchOrders();
        } catch (err: any) {
            alert(err.response?.data?.detail || "Could not complete void");
        }
    };

    // Handle Refund
    const handleConfirmRefund = async () => {
        if (!selectedOrder || refundAmountKES <= 0 || !refundReason.trim()) return;
        try {
            const res = await api.post(`/orders/${selectedOrder.id}/refund`, {
                refund_cents: Math.round(refundAmountKES * 100),
                refund_reason: refundReason,
            });
            setSelectedOrder(res.data);
            setShowRefundModal(false);
            setRefundAmountKES(0);
            setRefundReason("");
            await fetchOrders();
        } catch (err: any) {
            alert(err.response?.data?.detail || "Could not complete refund");
        }
    };

    // Handle Payment Collection
    const handleCollectPayment = async () => {
        if (!selectedOrder) return;
        try {
            const res = await api.patch(`/orders/${selectedOrder.id}/payment`, {
                payment_method: payMethod,
                is_paid: true,
            });
            setSelectedOrder(res.data);
            setShowPayModal(false);
            await fetchOrders();
        } catch (err: any) {
            alert(err.response?.data?.detail || "Could not update payment");
        }
    };

    // View Customer History
    const handleLoadCustomerHistory = async (order: Order) => {
        if (!order.customer_phone) return;
        setHistoryLoading(true);
        try {
            const res = await api.get(`/orders/${order.id}/customer-history`);
            setCustomerHistory(res.data);
        } catch {}
        setHistoryLoading(false);
    };

    const statusBadge = (status: string) => {
        switch (status) {
            case "pending":
                return "bg-blue-950/80 text-blue-300 border-blue-800";
            case "prep":
                return "bg-amber-950/80 text-amber-300 border-amber-800";
            case "ready":
                return "bg-emerald-950/80 text-emerald-300 border-emerald-800";
            case "served":
                return "bg-stone-800 text-stone-300 border-stone-700";
            case "cancelled":
                return "bg-red-950/80 text-red-300 border-red-800";
            default:
                return "bg-stone-800 text-stone-400 border-stone-700";
        }
    };

    return (
        <div className="flex h-[calc(100vh-4rem)] bg-stone-950 text-stone-100 overflow-hidden">
            {/* MAIN ORDERS LIST */}
            <div className="flex-1 flex flex-col p-4 overflow-hidden border-r border-stone-800/80">
                {/* Page Title & KPI Strip */}
                <div className="space-y-3 pb-3 border-b border-stone-800/80">
                    <div className="flex items-center justify-between">
                        <div>
                            <h1 className="text-lg font-bold">Orders Management</h1>
                            <p className="text-xs text-stone-400">Live order audit & register &bull; {today} Africa/Nairobi</p>
                        </div>
                    </div>

                    {/* KPI Strip */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div className="bg-stone-900/80 border border-stone-800 rounded-xl p-3">
                            <span className="text-[11px] text-stone-400">Today&apos;s Revenue</span>
                            <p className="text-base font-bold text-emerald-400 mt-0.5">{formatKES(todayRevenue)}</p>
                        </div>
                        <div className="bg-stone-900/80 border border-stone-800 rounded-xl p-3">
                            <span className="text-[11px] text-stone-400">Today&apos;s Tickets</span>
                            <p className="text-base font-bold text-stone-100 mt-0.5">{todayOrders.length}</p>
                        </div>
                        <div className="bg-stone-900/80 border border-stone-800 rounded-xl p-3">
                            <span className="text-[11px] text-stone-400">Unpaid Tickets</span>
                            <p className="text-base font-bold text-amber-400 mt-0.5">{unpaidCount}</p>
                        </div>
                        <div className="bg-stone-900/80 border border-stone-800 rounded-xl p-3">
                            <span className="text-[11px] text-stone-400">Avg Ticket Value</span>
                            <p className="text-base font-bold text-stone-200 mt-0.5">{formatKES(avgTicket)}</p>
                        </div>
                    </div>
                </div>

                {/* Filter & Search Toolbar */}
                <div className="flex flex-wrap items-center gap-2 py-3 border-b border-stone-800/80">
                    <div className="relative flex-1 min-w-[200px]">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-stone-400" />
                        <input
                            type="text"
                            placeholder="Search by Ticket #, Customer, or Phone..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full bg-stone-900 border border-stone-800 rounded-lg pl-9 pr-3 py-1.5 text-xs text-stone-100 placeholder-stone-500 focus:outline-none focus:border-amber-500/60"
                        />
                    </div>
                    <select
                        value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value)}
                        className="bg-stone-900 border border-stone-800 rounded-lg px-2.5 py-1.5 text-xs text-stone-200"
                    >
                        <option value="all">All Statuses</option>
                        <option value="pending">Pending</option>
                        <option value="prep">Cooking</option>
                        <option value="ready">Ready</option>
                        <option value="served">Served</option>
                        <option value="cancelled">Cancelled</option>
                    </select>

                    <select
                        value={channelFilter}
                        onChange={(e) => setChannelFilter(e.target.value)}
                        className="bg-stone-900 border border-stone-800 rounded-lg px-2.5 py-1.5 text-xs text-stone-200"
                    >
                        <option value="all">All Channels</option>
                        <option value="walk_in">Walk-in</option>
                        <option value="app">Customer App</option>
                        <option value="uber_eats">Uber Eats</option>
                        <option value="glovo">Glovo</option>
                        <option value="bolt_food">Bolt Food</option>
                    </select>

                    <button
                        onClick={() => setUnpaidOnly(!unpaidOnly)}
                        className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
                            unpaidOnly
                                ? "bg-amber-500/20 border-amber-500 text-amber-300"
                                : "bg-stone-900 border-stone-800 text-stone-400 hover:text-stone-200"
                        }`}
                    >
                        Unpaid Only
                    </button>
                </div>

                {/* Orders List Table */}
                <div className="flex-1 overflow-y-auto pt-2">
                    {loading ? (
                        <div className="p-8 text-center text-xs text-stone-500">Loading orders...</div>
                    ) : filteredOrders.length === 0 ? (
                        <div className="p-12 text-center text-xs text-stone-500">
                            <ShoppingBag className="w-8 h-8 mx-auto mb-2 opacity-40" />
                            No orders match the current filter.
                        </div>
                    ) : (
                        <div className="space-y-1.5">
                            {filteredOrders.map((order) => {
                                const isSelected = selectedOrder?.id === order.id;
                                const timeStr = new Date(order.created_at).toLocaleTimeString([], {
                                    hour: "2-digit",
                                    minute: "2-digit",
                                });
                                return (
                                    <div
                                        key={order.id}
                                        onClick={() => {
                                            setSelectedOrder(order);
                                            setCustomerHistory(null);
                                        }}
                                        className={`p-3 rounded-xl border flex items-center justify-between cursor-pointer transition-all ${
                                            isSelected
                                                ? "bg-amber-500/10 border-amber-500/80 shadow-md"
                                                : "bg-stone-900/60 border-stone-800/80 hover:bg-stone-900 hover:border-stone-700"
                                        }`}
                                    >
                                        <div className="flex items-center gap-3">
                                            <span className="text-xs font-mono font-bold text-stone-300 w-12">
                                                #{order.id}
                                            </span>
                                            <div>
                                                <div className="flex items-center gap-2">
                                                    <span className="text-xs font-semibold text-stone-100">
                                                        {order.customer_name || "Walk-in Customer"}
                                                    </span>
                                                    {order.table_number && (
                                                        <span className="text-[10px] bg-stone-800 text-stone-400 px-1.5 py-0.5 rounded">
                                                            Table {order.table_number}
                                                        </span>
                                                    )}
                                                </div>
                                                <div className="flex items-center gap-2 text-[11px] text-stone-500 mt-0.5">
                                                    <span>{timeStr}</span>
                                                    <span>&bull;</span>
                                                    <span>{order.items.length} items</span>
                                                    <span>&bull;</span>
                                                    <span className="capitalize">{order.delivery_channel.replace("_", " ")}</span>
                                                </div>
                                            </div>
                                        </div>

                                        <div className="flex items-center gap-3">
                                            <div className="text-right">
                                                <span className="text-xs font-bold text-stone-100 block">
                                                    {formatKES(order.total)}
                                                </span>
                                                <span
                                                    className={`text-[10px] font-bold px-1.5 py-0.2 rounded border ${
                                                        order.is_paid
                                                            ? "bg-emerald-950 text-emerald-400 border-emerald-800"
                                                            : "bg-amber-950 text-amber-400 border-amber-800"
                                                    }`}
                                                >
                                                    {order.is_paid ? "PAID" : "UNPAID"}
                                                </span>
                                            </div>
                                            <span
                                                className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded border ${statusBadge(
                                                    order.status
                                                )}`}
                                            >
                                                {order.status}
                                            </span>
                                            <ChevronRight className="w-4 h-4 text-stone-500" />
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            </div>

            {/* RIGHT: ORDER DETAIL DRAWER */}
            {selectedOrder ? (
                <div className="w-96 lg:w-[440px] bg-stone-900 border-l border-stone-800 flex flex-col overflow-hidden">
                    {/* Drawer Header */}
                    <div className="p-4 border-b border-stone-800 flex items-center justify-between bg-stone-900/90">
                        <div>
                            <div className="flex items-center gap-2">
                                <h3 className="text-sm font-bold text-stone-100">Ticket #{selectedOrder.id}</h3>
                                <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded border ${statusBadge(selectedOrder.status)}`}>
                                    {selectedOrder.status}
                                </span>
                            </div>
                            <p className="text-[11px] text-stone-400 mt-0.5">
                                Placed at {new Date(selectedOrder.created_at).toLocaleString()}
                            </p>
                        </div>
                        <button onClick={() => setSelectedOrder(null)} className="text-stone-400 hover:text-stone-200">
                            <X className="w-5 h-5" />
                        </button>
                    </div>

                    {/* Drawer Content */}
                    <div className="flex-1 overflow-y-auto p-4 space-y-4">
                        {/* Customer & Channel Info */}
                        <div className="p-3 bg-stone-950 rounded-xl border border-stone-800/80 space-y-1 text-xs">
                            <div className="flex justify-between">
                                <span className="text-stone-500">Customer:</span>
                                <span className="font-semibold text-stone-200">{selectedOrder.customer_name || "Walk-in"}</span>
                            </div>
                            {selectedOrder.customer_phone && (
                                <div className="flex justify-between items-center">
                                    <span className="text-stone-500">Phone:</span>
                                    <div className="flex items-center gap-1.5">
                                        <span className="font-mono text-stone-300">{selectedOrder.customer_phone}</span>
                                        <button
                                            onClick={() => handleLoadCustomerHistory(selectedOrder)}
                                            className="text-[10px] bg-stone-800 text-amber-400 px-1.5 py-0.5 rounded hover:bg-stone-700 flex items-center gap-1"
                                        >
                                            <History className="w-2.5 h-2.5" /> History
                                        </button>
                                    </div>
                                </div>
                            )}
                            {selectedOrder.table_number && (
                                <div className="flex justify-between">
                                    <span className="text-stone-500">Table Number:</span>
                                    <span className="font-bold text-amber-400">{selectedOrder.table_number}</span>
                                </div>
                            )}
                            <div className="flex justify-between">
                                <span className="text-stone-500">Order Channel:</span>
                                <span className="capitalize text-stone-300">{selectedOrder.delivery_channel.replace("_", " ")}</span>
                            </div>
                        </div>

                        {/* Customer History Accordion (if clicked) */}
                        {customerHistory && (
                            <div className="p-3 bg-stone-950 rounded-xl border border-amber-900/50 space-y-2 text-xs">
                                <div className="flex justify-between font-bold text-amber-400 border-b border-stone-800 pb-1">
                                    <span>Customer Profile</span>
                                    <span>{customerHistory.order_count} Past Orders</span>
                                </div>
                                <div className="flex justify-between text-stone-400">
                                    <span>Total Lifetime Spend:</span>
                                    <span className="font-bold text-emerald-400">{formatKES(customerHistory.total_spent_cents)}</span>
                                </div>
                            </div>
                        )}

                        {/* Items Breakdown */}
                        <div className="space-y-2">
                            <h4 className="text-xs font-bold uppercase tracking-wider text-stone-400">Ordered Items</h4>
                            <div className="space-y-1.5">
                                {selectedOrder.items.map((it) => (
                                    <div
                                        key={it.id}
                                        className={`p-2.5 rounded-lg border text-xs flex items-start justify-between gap-2 ${
                                            it.is_voided
                                                ? "bg-red-950/20 border-red-900/40 opacity-60 line-through"
                                                : "bg-stone-950/60 border-stone-800"
                                        }`}
                                    >
                                        <div>
                                            <span className="font-semibold text-stone-200">
                                                {it.quantity}x {it.item_name}
                                            </span>
                                            {it.modifiers && it.modifiers.length > 0 && (
                                                <p className="text-[10px] text-stone-400">
                                                    {it.modifiers.map((m) => `+${m.name} (${formatKES(m.price_delta_cents)})`).join(", ")}
                                                </p>
                                            )}
                                            {it.notes && <p className="text-[10px] text-amber-300 italic">{it.notes}</p>}
                                            {it.is_voided && (
                                                <span className="text-[10px] text-red-400 block mt-0.5">
                                                    Voided: {it.void_reason}
                                                </span>
                                            )}
                                        </div>
                                        <div className="text-right flex items-center gap-2">
                                            <span className="font-bold text-stone-200">{formatKES(it.unit_price * it.quantity)}</span>
                                            {!it.is_voided && selectedOrder.status !== "cancelled" && (
                                                <button
                                                    onClick={() => {
                                                        setVoidingTarget({ type: "item", id: it.id });
                                                        setShowVoidModal(true);
                                                    }}
                                                    className="text-[10px] text-red-400 hover:text-red-300 p-1"
                                                    title="Void this line item"
                                                >
                                                    Void
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Financial Audit Trail */}
                        <div className="p-3 bg-stone-950 rounded-xl border border-stone-800 space-y-1.5 text-xs">
                            <div className="flex justify-between text-stone-400">
                                <span>Subtotal</span>
                                <span>{formatKES(selectedOrder.total + selectedOrder.discount_cents)}</span>
                            </div>
                            {selectedOrder.discount_cents > 0 && (
                                <div className="flex justify-between text-emerald-400">
                                    <span>Discount ({selectedOrder.discount_reason || "Promo"})</span>
                                    <span>-{formatKES(selectedOrder.discount_cents)}</span>
                                </div>
                            )}
                            {selectedOrder.refund_cents > 0 && (
                                <div className="flex justify-between text-red-400 font-semibold">
                                    <span>Refunded ({selectedOrder.refund_reason})</span>
                                    <span>-{formatKES(selectedOrder.refund_cents)}</span>
                                </div>
                            )}
                            <div className="flex justify-between font-bold text-stone-100 pt-1 border-t border-stone-800 text-sm">
                                <span>Total Paid / Due</span>
                                <span className="text-amber-400">{formatKES(selectedOrder.total)}</span>
                            </div>
                        </div>

                        {/* Payments Breakdown */}
                        {selectedOrder.payments && selectedOrder.payments.length > 0 && (
                            <div className="space-y-1.5">
                                <h4 className="text-xs font-bold uppercase tracking-wider text-stone-400">Payment Tenders</h4>
                                {selectedOrder.payments.map((p) => (
                                    <div key={p.id} className="p-2 bg-stone-950 rounded-lg border border-stone-800 flex justify-between text-xs">
                                        <span className="capitalize font-semibold text-stone-300">{p.payment_method}</span>
                                        <div className="text-right">
                                            <span className="font-bold text-emerald-400">{formatKES(p.amount_cents)}</span>
                                            {p.reference && <span className="text-[10px] text-stone-500 block">{p.reference}</span>}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* Order Notes */}
                        {selectedOrder.notes && (
                            <div className="p-2.5 bg-amber-950/20 border border-amber-900/40 rounded-lg text-xs text-amber-300">
                                Note: {selectedOrder.notes}
                            </div>
                        )}
                    </div>

                    {/* Drawer Action Bar */}
                    <div className="p-4 border-t border-stone-800 bg-stone-950/90 grid grid-cols-2 gap-2">
                        {!selectedOrder.is_paid && selectedOrder.status !== "cancelled" && (
                            <button
                                onClick={() => setShowPayModal(true)}
                                className="col-span-2 py-2.5 rounded-xl bg-emerald-500 text-stone-950 font-bold text-xs hover:bg-emerald-400 flex items-center justify-center gap-1.5"
                            >
                                <DollarSign className="w-3.5 h-3.5" /> Take Payment ({formatKES(selectedOrder.total)})
                            </button>
                        )}
                        <button
                            onClick={() => window.print()}
                            className="py-2 rounded-xl bg-stone-800 border border-stone-700 text-xs font-semibold text-stone-200 hover:bg-stone-700 flex items-center justify-center gap-1"
                        >
                            <Printer className="w-3 h-3 text-amber-400" /> Reprint
                        </button>
                        <button
                            onClick={async () => {
                                await api.post(`/orders/${selectedOrder.id}/resend-kitchen`);
                                alert("Order resent to Kitchen Display");
                                await fetchOrders();
                            }}
                            className="py-2 rounded-xl bg-stone-800 border border-stone-700 text-xs font-semibold text-stone-200 hover:bg-stone-700 flex items-center justify-center gap-1"
                        >
                            <Send className="w-3 h-3 text-blue-400" /> Resend KDS
                        </button>
                        {selectedOrder.status !== "cancelled" && (
                            <>
                                <button
                                    onClick={() => {
                                        setRefundAmountKES(selectedOrder.total / 100);
                                        setShowRefundModal(true);
                                    }}
                                    className="py-2 rounded-xl bg-stone-800 border border-stone-700 text-xs font-semibold text-amber-400 hover:bg-stone-700 flex items-center justify-center gap-1"
                                >
                                    <RotateCcw className="w-3 h-3" /> Refund
                                </button>
                                <button
                                    onClick={() => {
                                        setVoidingTarget({ type: "order", id: selectedOrder.id });
                                        setShowVoidModal(true);
                                    }}
                                    className="py-2 rounded-xl bg-red-950/60 border border-red-800/80 text-xs font-semibold text-red-300 hover:bg-red-900 flex items-center justify-center gap-1"
                                >
                                    <AlertOctagon className="w-3 h-3" /> Void Ticket
                                </button>
                            </>
                        )}
                    </div>
                </div>
            ) : null}

            {/* VOID REASON MODAL */}
            {showVoidModal && (
                <div className="fixed inset-0 bg-stone-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-stone-900 border border-stone-800 rounded-2xl max-w-sm w-full p-5 flex flex-col gap-4">
                        <div className="flex items-center justify-between">
                            <h3 className="text-sm font-bold text-red-400">
                                {voidingTarget?.type === "order" ? "Void Entire Order" : "Void Item"}
                            </h3>
                            <button onClick={() => setShowVoidModal(false)} className="text-stone-400">
                                <X className="w-4 h-4" />
                            </button>
                        </div>
                        <p className="text-xs text-stone-400">
                            A void reason is required for internal financial audit and stock reconciliation.
                        </p>
                        <div>
                            <label className="text-xs text-stone-300 block mb-1">Reason for Void</label>
                            <input
                                type="text"
                                placeholder="e.g. Customer changed mind / duplicate ring-up / spilled"
                                value={voidReason}
                                onChange={(e) => setVoidReason(e.target.value)}
                                className="w-full bg-stone-950 border border-stone-800 rounded-lg px-3 py-2 text-xs text-stone-100 placeholder-stone-500 focus:outline-none focus:border-red-500/60"
                            />
                        </div>
                        <div className="flex gap-2 pt-2 border-t border-stone-800">
                            <button
                                onClick={() => setShowVoidModal(false)}
                                className="flex-1 py-2 rounded-xl border border-stone-700 text-xs text-stone-400"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleConfirmVoid}
                                disabled={!voidReason.trim()}
                                className="flex-1 py-2 rounded-xl bg-red-600 text-white font-bold text-xs hover:bg-red-500 disabled:opacity-40"
                            >
                                Confirm Void
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* REFUND MODAL */}
            {showRefundModal && (
                <div className="fixed inset-0 bg-stone-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-stone-900 border border-stone-800 rounded-2xl max-w-sm w-full p-5 flex flex-col gap-4">
                        <div className="flex items-center justify-between">
                            <h3 className="text-sm font-bold text-amber-400">Process Refund</h3>
                            <button onClick={() => setShowRefundModal(false)} className="text-stone-400">
                                <X className="w-4 h-4" />
                            </button>
                        </div>
                        <div>
                            <label className="text-xs text-stone-300 block mb-1">Refund Amount (KES)</label>
                            <input
                                type="number"
                                value={refundAmountKES || ""}
                                onChange={(e) => setRefundAmountKES(Number(e.target.value))}
                                className="w-full bg-stone-950 border border-stone-800 rounded-lg px-3 py-2 text-sm text-stone-100"
                            />
                        </div>
                        <div>
                            <label className="text-xs text-stone-300 block mb-1">Reason for Refund</label>
                            <input
                                type="text"
                                placeholder="e.g. Overcharged / wrong dish / service recovery"
                                value={refundReason}
                                onChange={(e) => setRefundReason(e.target.value)}
                                className="w-full bg-stone-950 border border-stone-800 rounded-lg px-3 py-2 text-xs text-stone-100 placeholder-stone-500"
                            />
                        </div>
                        <div className="flex gap-2 pt-2 border-t border-stone-800">
                            <button
                                onClick={() => setShowRefundModal(false)}
                                className="flex-1 py-2 rounded-xl border border-stone-700 text-xs text-stone-400"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleConfirmRefund}
                                disabled={refundAmountKES <= 0 || !refundReason.trim()}
                                className="flex-1 py-2 rounded-xl bg-amber-500 text-stone-950 font-bold text-xs hover:bg-amber-400 disabled:opacity-40"
                            >
                                Submit Refund
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* TAKE PAYMENT MODAL */}
            {showPayModal && selectedOrder && (
                <div className="fixed inset-0 bg-stone-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-stone-900 border border-stone-800 rounded-2xl max-w-sm w-full p-5 flex flex-col gap-4">
                        <div className="flex items-center justify-between">
                            <h3 className="text-sm font-bold text-stone-100">Collect Order Payment</h3>
                            <button onClick={() => setShowPayModal(false)} className="text-stone-400">
                                <X className="w-4 h-4" />
                            </button>
                        </div>
                        <div className="p-3 bg-stone-950 rounded-xl border border-stone-800 flex justify-between text-xs">
                            <span className="text-stone-400">Amount Due:</span>
                            <span className="font-bold text-base text-amber-400">{formatKES(selectedOrder.total)}</span>
                        </div>
                        <div className="grid grid-cols-3 gap-2">
                            {["mpesa", "cash", "card"].map((m) => (
                                <button
                                    key={m}
                                    onClick={() => setPayMethod(m)}
                                    className={`py-2 rounded-lg text-xs font-semibold capitalize border ${
                                        payMethod === m
                                            ? "bg-amber-500/20 border-amber-500 text-amber-300"
                                            : "bg-stone-950 border-stone-800 text-stone-400"
                                    }`}
                                >
                                    {m}
                                </button>
                            ))}
                        </div>
                        <button
                            onClick={handleCollectPayment}
                            className="w-full py-2.5 rounded-xl bg-emerald-500 text-stone-950 font-bold text-xs hover:bg-emerald-400"
                        >
                            Mark Paid & Issue Receipt
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
