"use client";

import { useState } from "react";
import api from "@/lib/api";
import { motion, AnimatePresence } from "framer-motion";
import { Truck } from "lucide-react";
import FormField from "@/components/ui/FormField";
import type { ToastType } from "@/components/ui/Toast";
import { getErrorMessage } from "@/lib/errors";
import type { PurchaseOrder } from "./types";

interface PurchaseOrdersPanelProps {
    orders: PurchaseOrder[];
    submitting: boolean;
    setSubmitting: (v: boolean) => void;
    showToast: (message: string, type?: ToastType) => void;
    fetchAll: () => Promise<void>;
}

export default function PurchaseOrdersPanel({ orders, submitting, setSubmitting, showToast, fetchAll }: PurchaseOrdersPanelProps) {
    const [receivingId, setReceivingId] = useState<number | null>(null);
    const [receiveQty, setReceiveQty] = useState("");

    const handleApprove = async (poId: number) => {
        setSubmitting(true);
        try {
            await api.post(`/purchase-orders/${poId}/approve`);
            showToast("Approved and sent to supplier");
            await fetchAll();
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to approve"), "error");
        }
        setSubmitting(false);
    };

    const handleReceive = async (poId: number) => {
        if (!receiveQty) return;
        setSubmitting(true);
        try {
            const res = await api.post(`/purchase-orders/${poId}/receive`, {
                quantity_received: parseFloat(receiveQty),
            });
            showToast(
                res.data.status === "partial"
                    ? "Recorded — delivery was short, flagged for review"
                    : "Delivery recorded, stock updated"
            );
            setReceivingId(null);
            setReceiveQty("");
            await fetchAll();
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to record delivery"), "error");
        }
        setSubmitting(false);
    };

    const pendingOrders = orders.filter((o) => o.status === "PENDING");
    const sentOrders = orders.filter((o) => o.status === "SENT");
    const pastOrders = orders.filter((o) => !["PENDING", "SENT"].includes(o.status));

    return (
        <>
            {/* Purchase orders needing approval */}
            {pendingOrders.length > 0 && (
                <div className="bg-surface border border-accent/20 rounded-xl">
                    <div className="px-4 py-3 border-b border-border flex items-center gap-2">
                        <Truck className="w-3.5 h-3.5 text-accent" />
                        <p className="text-xs font-semibold text-text">Awaiting your approval</p>
                    </div>
                    <div className="divide-y divide-border">
                        {pendingOrders.map((po) => (
                            <div key={po.id} className="px-4 py-3 flex items-center justify-between">
                                <div>
                                    <p className="text-sm text-text">
                                        #{po.id} · {po.quantity_ordered}{po.unit} {po.item_name} from {po.supplier_name}
                                    </p>
                                    <p className="text-[10px] text-text-dim mt-0.5">{po.notes}</p>
                                </div>
                                <button onClick={() => handleApprove(po.id)} disabled={submitting}
                                    className="bg-accent text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50 whitespace-nowrap">
                                    {submitting ? "..." : "Approve & Send"}
                                </button>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Sent, awaiting delivery */}
            {sentOrders.length > 0 && (
                <div className="bg-surface border border-border rounded-xl">
                    <div className="px-4 py-3 border-b border-border">
                        <p className="text-xs font-semibold text-text">Sent — awaiting delivery</p>
                    </div>
                    <div className="divide-y divide-border">
                        {sentOrders.map((po) => (
                            <div key={po.id} className="px-4 py-3">
                                <div className="flex items-center justify-between">
                                    <p className="text-sm text-text">
                                        #{po.id} · {po.quantity_ordered}{po.unit} {po.item_name} from {po.supplier_name}
                                    </p>
                                    <button
                                        onClick={() => { setReceivingId(receivingId === po.id ? null : po.id); setReceiveQty(String(po.quantity_ordered)); }}
                                        className="text-[10px] px-2 py-1 rounded bg-surface-hover text-text-muted hover:text-success transition-all">
                                        Record delivery
                                    </button>
                                </div>
                                <AnimatePresence>
                                    {receivingId === po.id && (
                                        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                            className="mt-2 flex gap-2 items-center">
                                            <FormField
                                                label="Quantity actually received"
                                                srOnlyLabel
                                                placeholder="Quantity actually received"
                                                value={receiveQty}
                                                onChange={(e) => setReceiveQty(e.target.value)}
                                                type="number"
                                                className="flex-1 bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none" />
                                            <button onClick={() => handleReceive(po.id)} disabled={!receiveQty || submitting}
                                                className="bg-success text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                                                {submitting ? "..." : "Confirm"}
                                            </button>
                                        </motion.div>
                                    )}
                                </AnimatePresence>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Order history */}
            {pastOrders.length > 0 && (
                <div className="bg-surface border border-border rounded-xl">
                    <div className="px-4 py-3 border-b border-border">
                        <p className="text-xs font-semibold text-text">History</p>
                    </div>
                    <div className="divide-y divide-border">
                        {pastOrders.slice(0, 20).map((po) => (
                            <div key={po.id} className="px-4 py-2.5 flex items-center justify-between">
                                <p className="text-xs text-text-muted">
                                    #{po.id} · {po.item_name} from {po.supplier_name}
                                </p>
                                <span className={`text-[10px] px-1.5 py-0.5 rounded ${po.status === "DELIVERED" ? "bg-success/10 text-success" : po.status === "PARTIAL" ? "bg-warning/10 text-warning" : "bg-surface-hover text-text-dim"}`}>
                                    {po.status.toLowerCase()}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </>
    );
}
