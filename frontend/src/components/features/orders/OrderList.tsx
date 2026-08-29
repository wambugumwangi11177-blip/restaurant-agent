"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { motion, AnimatePresence } from "framer-motion";
import { ShoppingBag, Banknote, Smartphone, CreditCard, Ban } from "lucide-react";
import { useToast } from "@/components/ui/Toast";
import FormField from "@/components/ui/FormField";
import OrderInsightsPanel from "./OrderInsightsPanel";
import { getErrorMessage } from "@/lib/errors";
import type { Order, OrderAiData } from "./types";

/**
 * Order list + light analytics — extracted from the original
 * dashboard/orders/page.tsx. Status advancement (pending -> prep -> ready ->
 * served) stays KDSBoard's job and new-order entry stays POSWorkspace's job —
 * this adds the two manual corrections that belong to an order already
 * placed: recording how it was actually paid for, and cancelling one with a
 * reason. Reused unmodified by every tier with `orders` access (directive
 * 015: Owner/Manager/Supervisor/Waiter RW, Controller/Kitchen R); the write
 * actions below simply 403 server-side for a read-only tier, matching every
 * other workspace's pattern. /ai/revenue-forecast is Manager/Controller-only
 * server-side; other tiers simply see the insights panel absent, handled by
 * the existing .catch(() => ({ data: null })).
 *
 * The trends/forecast/anomalies card is extracted into OrderInsightsPanel
 * (pure display) to keep this file focused on data fetching + order actions.
 */
export default function OrderList() {
    const [orders, setOrders] = useState<Order[]>([]);
    const [aiData, setAiData] = useState<OrderAiData | null>(null);
    const [loading, setLoading] = useState(true);
    const { showToast, toastNode } = useToast();
    const [submitting, setSubmitting] = useState(false);
    const [payingId, setPayingId] = useState<number | null>(null);
    const [payMethod, setPayMethod] = useState("cash");
    const [cancellingId, setCancellingId] = useState<number | null>(null);
    const [cancelReason, setCancelReason] = useState("");

    const fetchData = () => {
        Promise.all([
            api.get("/orders/").catch(() => ({ data: [] })),
            api.get("/ai/revenue-forecast").catch(() => ({ data: null })),
        ]).then(([ordersRes, aiRes]) => {
            setOrders(Array.isArray(ordersRes.data) ? ordersRes.data : []);
            setAiData(aiRes.data);
            setLoading(false);
        });
    };

    useEffect(() => { fetchData(); }, []);

    const handleRecordPayment = async (orderId: number) => {
        setSubmitting(true);
        try {
            await api.post(`/orders/${orderId}/payment`, { payment_method: payMethod, is_paid: true });
            showToast("Payment recorded");
            setPayingId(null);
            fetchData();
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to record payment"), "error");
        }
        setSubmitting(false);
    };

    const handleCancelOrder = async (orderId: number) => {
        setSubmitting(true);
        try {
            if (cancelReason.trim()) {
                const order = orders.find((o) => o.id === orderId);
                const note = `Cancelled: ${cancelReason.trim()}`;
                await api.post(`/orders/${orderId}/details`, {
                    notes: order?.notes ? `${order.notes} | ${note}` : note,
                });
            }
            await api.post(`/orders/${orderId}/status`, { status: "cancelled" });
            showToast("Order cancelled");
            setCancellingId(null);
            setCancelReason("");
            fetchData();
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to cancel order"), "error");
        }
        setSubmitting(false);
    };

    if (loading) {
        return (
            <div className="space-y-3">
                {[...Array(5)].map((_, i) => (
                    <div key={i} className="bg-surface rounded-xl h-16 animate-pulse" />
                ))}
            </div>
        );
    }

    const today = new Date().toISOString().split("T")[0];
    const todayOrders = orders.filter((o) => o.created_at?.startsWith(today));
    const pendingCount = orders.filter((o) => o.status === "pending" || o.status === "prep").length;
    const todayRevenue = todayOrders.reduce((s: number, o) => s + (o.total || 0), 0);

    const trends = aiData?.trends || { total_revenue: 0, avg_order_value: 0 };
    const forecast = aiData?.forecast || [];
    const anomalies = aiData?.anomalies || [];

    return (
        <div className="space-y-5">
            {toastNode}

            <div>
                <h1 className="text-xl font-bold text-text">Orders</h1>
                <p className="text-sm text-text-dim mt-0.5">
                    Live from your POS &amp; KDS
                </p>
            </div>

            {/* Today at a glance */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="bg-surface border border-border rounded-xl p-4">
                    <p className="text-xs text-text-dim">Today&apos;s Sales</p>
                    <p className="text-lg font-bold text-success mt-1">{formatKES(todayRevenue)}</p>
                </div>
                <div className="bg-surface border border-border rounded-xl p-4">
                    <p className="text-xs text-text-dim">Orders</p>
                    <p className="text-lg font-bold text-text mt-1">{todayOrders.length}</p>
                </div>
                <div className="bg-surface border border-border rounded-xl p-4">
                    <p className="text-xs text-text-dim">In the Kitchen</p>
                    <p className="text-lg font-bold text-accent mt-1">{pendingCount}</p>
                </div>
            </div>

            <OrderInsightsPanel trends={trends} forecast={forecast} anomalies={anomalies} />

            {/* Order List */}
            <div className="bg-surface border border-border rounded-xl">
                <div className="px-4 py-3 border-b border-surface-hover">
                    <h2 className="text-sm font-semibold text-text">Recent Orders</h2>
                </div>
                {orders.length === 0 ? (
                    <div className="px-5 py-10 text-center">
                        <ShoppingBag className="w-8 h-8 text-[#333] mx-auto mb-3" />
                        <p className="text-sm text-text-dim">No orders yet — they&apos;ll show up here from your POS</p>
                    </div>
                ) : (
                    <div className="divide-y divide-surface-hover">
                        {orders.map((order, i) => {
                            const statusLabels: Record<string, string> = {
                                pending: "Waiting",
                                prep: "Cooking",
                                ready: "Ready",
                                served: "Served",
                                cancelled: "Cancelled",
                            };
                            const statusStyles: Record<string, string> = {
                                pending: "bg-warning/10 text-warning",
                                prep: "bg-info/10 text-info",
                                ready: "bg-success/10 text-success",
                                served: "bg-text-muted/10 text-text-muted",
                                cancelled: "bg-danger/10 text-danger",
                            };
                            const canAct = order.status !== "cancelled" && order.status !== "served";
                            return (
                                <motion.div key={order.id || i} initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                                    transition={{ delay: i * 0.03 }}
                                    className="px-4 py-3 hover:bg-surface-hover transition-colors">
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-3">
                                            <span className="text-sm font-mono text-text-dim">#{order.id}</span>
                                            <div>
                                                <p className="text-sm text-text">{order.customer_name || "Walk-in"}</p>
                                                <p className="text-xs text-text-dim mt-0.5">
                                                    {friendlyOrderType(order.order_type)}{order.table_number ? ` · Table ${order.table_number}` : ""}
                                                    {!order.is_paid && order.status !== "cancelled" ? " · Unpaid" : ""}
                                                </p>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            {canAct && (
                                                <div className="flex items-center gap-1">
                                                    {!order.is_paid && (
                                                        <button
                                                            onClick={() => { setPayingId(payingId === order.id ? null : order.id); setCancellingId(null); }}
                                                            className="text-[10px] px-2 py-1 rounded bg-surface-hover text-text-muted hover:text-success transition-all">
                                                            Record payment
                                                        </button>
                                                    )}
                                                    <button
                                                        onClick={() => { setCancellingId(cancellingId === order.id ? null : order.id); setPayingId(null); }}
                                                        className="text-[10px] px-2 py-1 rounded bg-surface-hover text-text-muted hover:text-danger transition-all">
                                                        Cancel
                                                    </button>
                                                </div>
                                            )}
                                            <div className="text-right">
                                                <p className="text-sm font-medium text-accent">{formatKES(order.total)}</p>
                                                <span className={`inline-block mt-1 px-2 py-0.5 rounded text-[10px] font-medium ${statusStyles[order.status] || statusStyles.pending}`}>
                                                    {statusLabels[order.status] || order.status}
                                                </span>
                                            </div>
                                        </div>
                                    </div>

                                    <AnimatePresence>
                                        {payingId === order.id && (
                                            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                                className="mt-2 flex gap-1.5 items-center overflow-hidden">
                                                {[
                                                    { v: "cash", label: "Cash", icon: Banknote },
                                                    { v: "mpesa", label: "M-Pesa", icon: Smartphone },
                                                    { v: "card", label: "Card", icon: CreditCard },
                                                ].map((p) => (
                                                    <button key={p.v} onClick={() => setPayMethod(p.v)}
                                                        className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-all ${payMethod === p.v
                                                            ? "bg-success/10 text-success border border-success/30"
                                                            : "bg-surface-hover text-text-muted border border-transparent"
                                                            }`}>
                                                        <p.icon className="w-3 h-3" />
                                                        {p.label}
                                                    </button>
                                                ))}
                                                <button onClick={() => handleRecordPayment(order.id)} disabled={submitting}
                                                    className="bg-success text-black rounded-lg px-3 py-1 text-xs font-semibold disabled:opacity-50">
                                                    {submitting ? "..." : "Confirm"}
                                                </button>
                                            </motion.div>
                                        )}
                                    </AnimatePresence>

                                    <AnimatePresence>
                                        {cancellingId === order.id && (
                                            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                                className="mt-2 flex gap-2 items-center overflow-hidden">
                                                <FormField
                                                    label="Cancellation reason"
                                                    srOnlyLabel
                                                    placeholder="Reason (optional)" value={cancelReason}
                                                    onChange={(e) => setCancelReason(e.target.value)}
                                                    className="flex-1 bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none" />
                                                <button onClick={() => handleCancelOrder(order.id)} disabled={submitting}
                                                    className="flex items-center gap-1 bg-danger text-white rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                                                    <Ban className="w-3 h-3" />
                                                    {submitting ? "..." : "Confirm Cancel"}
                                                </button>
                                            </motion.div>
                                        )}
                                    </AnimatePresence>
                                </motion.div>
                            );
                        })}
                    </div>
                )}
            </div>
        </div>
    );
}

function formatKES(cents: number) {
    if (!cents) return "KES 0";
    return `KES ${(cents / 100).toLocaleString("en-KE", { maximumFractionDigits: 0 })}`;
}

function friendlyOrderType(type: string) {
    const map: Record<string, string> = {
        dine_in: "Dine in",
        takeout: "Takeaway",
        delivery: "Delivery",
    };
    return map[type] || type || "Dine in";
}
