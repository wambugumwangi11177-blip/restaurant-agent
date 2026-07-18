"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { motion, AnimatePresence } from "framer-motion";
import { Package, ClipboardList, Check } from "lucide-react";

/**
 * Kitchen's own stock view — directive 017's "pull" requisition, the
 * missing frontend half. The backend has always allowed Kitchen to request
 * an ingredient from the store (routers/stock_custody.py's _CAN_REQUEST) and
 * confirm what arrives (_CAN_CONFIRM), but no Kitchen-tier page ever called
 * either endpoint: /staff/kitchen only rendered KDSBoard. This is
 * deliberately narrower than InventoryWorkspace (no add/receive/adjust/push
 * a transfer — Kitchen has read-only inventory access per directive 015's
 * matrix, not write) rather than reusing that full workspace and hiding
 * buttons after the fact.
 */
export default function KitchenStockPanel() {
    const [items, setItems] = useState<any[]>([]);
    const [transfers, setTransfers] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    const [showRequestForm, setShowRequestForm] = useState(false);
    const [requestItemId, setRequestItemId] = useState("");
    const [confirmingId, setConfirmingId] = useState<number | null>(null);
    const [confirmQty, setConfirmQty] = useState("");

    const [submitting, setSubmitting] = useState(false);
    const [toast, setToast] = useState("");

    const showToast = (msg: string) => {
        setToast(msg);
        setTimeout(() => setToast(""), 3000);
    };

    const fetchData = async () => {
        const [invRes, transfersRes] = await Promise.all([
            api.get("/inventory/").catch(() => ({ data: [] })),
            api.get("/stock/transfers").catch(() => ({ data: [] })),
        ]);
        setItems(Array.isArray(invRes.data) ? invRes.data : []);
        setTransfers(
            Array.isArray(transfersRes.data)
                ? transfersRes.data.filter((t: any) => t.status === "requested" || t.status === "pending")
                : []
        );
        setLoading(false);
    };

    useEffect(() => { fetchData(); }, []);

    const handleRequestStock = async () => {
        if (!requestItemId) return;
        setSubmitting(true);
        try {
            await api.post("/stock/transfers/request", {
                inventory_item_id: parseInt(requestItemId),
            });
            showToast("Request sent to the store");
            setShowRequestForm(false);
            setRequestItemId("");
            await fetchData();
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to send request");
        }
        setSubmitting(false);
    };

    const handleConfirmTransfer = async (transferId: number) => {
        if (!confirmQty) return;
        setSubmitting(true);
        try {
            const res = await api.post(`/stock/transfers/${transferId}/confirm`, {
                confirmed_quantity: parseFloat(confirmQty),
            });
            showToast(
                res.data.status === "disputed"
                    ? "Quantity doesn't match what was sent — flagged for review"
                    : "Transfer confirmed"
            );
            setConfirmingId(null);
            setConfirmQty("");
            await fetchData();
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to confirm");
        }
        setSubmitting(false);
    };

    if (loading) {
        return (
            <div className="space-y-3">
                {[...Array(3)].map((_, i) => (
                    <div key={i} className="bg-[var(--surface)] rounded-xl h-14 animate-pulse" />
                ))}
            </div>
        );
    }

    return (
        <div className="space-y-5">
            <AnimatePresence>
                {toast && (
                    <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}
                        className="fixed top-4 right-4 z-50 bg-[var(--success)]/10 border border-[var(--success)]/30 rounded-xl px-5 py-3 flex items-center gap-2">
                        <Check className="w-4 h-4 text-[var(--success)]" />
                        <span className="text-sm text-[var(--success)]">{toast}</span>
                    </motion.div>
                )}
            </AnimatePresence>

            <div>
                <h1 className="text-xl font-bold text-[var(--text)]">Stock</h1>
                <p className="text-sm text-[var(--text-dim)] mt-0.5">
                    Running low on something? Request it from the store — the storekeeper gets notified right away.
                </p>
            </div>

            {/* Request from store */}
            <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl">
                <div className="px-4 py-3 border-b border-[var(--surface-hover)] flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <ClipboardList className="w-3.5 h-3.5 text-[var(--accent)]" />
                        <p className="text-xs font-semibold text-[var(--text)]">Request from store</p>
                    </div>
                    <button onClick={() => setShowRequestForm(!showRequestForm)}
                        className="text-[10px] px-2 py-1 rounded bg-[var(--surface-hover)] text-[var(--text-muted)] hover:text-[var(--accent)] transition-all">
                        {showRequestForm ? "Cancel" : "What do you need?"}
                    </button>
                </div>
                <AnimatePresence>
                    {showRequestForm && (
                        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                            className="px-4 py-3 flex gap-2 items-center overflow-hidden">
                            <select value={requestItemId} onChange={(e) => setRequestItemId(e.target.value)}
                                className="flex-1 bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] focus:outline-none">
                                <option value="">Select an ingredient…</option>
                                {items.map((i) => <option key={i.id} value={i.id}>{i.item_name}</option>)}
                            </select>
                            <button onClick={handleRequestStock} disabled={!requestItemId || submitting}
                                className="bg-[var(--accent)] text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                                {submitting ? "..." : "Request"}
                            </button>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>

            {/* Pending requests / awaiting confirmation */}
            <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl">
                <div className="px-4 py-3 border-b border-[var(--surface-hover)]">
                    <p className="text-xs font-semibold text-[var(--text)]">Requests & deliveries</p>
                </div>
                <div className="divide-y divide-[var(--surface-hover)]">
                    {transfers.length === 0 ? (
                        <p className="text-xs text-[var(--text-dim)] text-center py-6">Nothing pending</p>
                    ) : (
                        transfers.map((t) => {
                            const isRequested = t.status === "requested";
                            return (
                                <div key={t.id} className="px-4 py-3">
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <p className="text-sm text-[var(--text)]">
                                                #{t.id} · {isRequested ? "requested" : `${t.quantity}${t.unit}`} {t.from_location} → {t.to_location}
                                            </p>
                                            <p className="text-[10px] text-[var(--text-dim)] mt-0.5">
                                                {isRequested ? "Waiting for the store to send it" : "Ready to collect — confirm what actually arrived"}
                                            </p>
                                        </div>
                                        {!isRequested && (
                                            <button
                                                onClick={() => { setConfirmingId(confirmingId === t.id ? null : t.id); setConfirmQty(String(t.quantity)); }}
                                                className="text-[10px] px-2 py-1 rounded bg-[var(--surface-hover)] text-[var(--text-muted)] hover:text-[var(--success)] transition-all">
                                                Confirm receipt
                                            </button>
                                        )}
                                    </div>
                                    <AnimatePresence>
                                        {confirmingId === t.id && (
                                            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                                className="mt-2 flex gap-2 items-center">
                                                <input placeholder="Actual quantity received" value={confirmQty} onChange={(e) => setConfirmQty(e.target.value)}
                                                    type="number" className="flex-1 bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] placeholder-[var(--text-dim)] focus:outline-none" />
                                                <button onClick={() => handleConfirmTransfer(t.id)} disabled={!confirmQty || submitting}
                                                    className="bg-[var(--success)] text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                                                    {submitting ? "..." : "Confirm"}
                                                </button>
                                            </motion.div>
                                        )}
                                    </AnimatePresence>
                                </div>
                            );
                        })
                    )}
                </div>
            </div>

            {/* Read-only stock levels */}
            <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl">
                <div className="px-4 py-3 border-b border-[var(--surface-hover)] flex items-center gap-2">
                    <Package className="w-3.5 h-3.5 text-[var(--accent)]" />
                    <p className="text-xs font-semibold text-[var(--text)]">Stock levels</p>
                </div>
                <div className="divide-y divide-[var(--surface-hover)]">
                    {items.length === 0 ? (
                        <p className="text-xs text-[var(--text-dim)] text-center py-8">No stock items tracked yet</p>
                    ) : (
                        items.map((item) => {
                            const isLow = item.quantity <= item.low_stock_threshold;
                            const isOut = item.quantity <= 0;
                            return (
                                <div key={item.id} className="px-4 py-3 flex items-center gap-3">
                                    <div className={`w-2 h-2 rounded-full flex-shrink-0 ${isOut ? "bg-[var(--danger)]" : isLow ? "bg-[var(--warning)]" : "bg-[var(--success)]"}`} />
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm text-[var(--text)]">{item.item_name}</p>
                                        <span className={`text-xs ${isLow ? "text-[var(--warning)]" : "text-[var(--text-muted)]"}`}>
                                            {item.quantity} {item.unit}
                                        </span>
                                    </div>
                                    {isOut && <span className="text-[10px] text-[var(--danger)] font-semibold">Out</span>}
                                    {!isOut && isLow && <span className="text-[10px] text-[var(--warning)] font-semibold">Low</span>}
                                </div>
                            );
                        })
                    )}
                </div>
            </div>
        </div>
    );
}
