"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { demoData, isDemoMode } from "@/lib/demo-data";
import { motion, AnimatePresence } from "framer-motion";
import {
    Package, AlertTriangle, Plus, TruckIcon,
    Minus, X, Check, ArrowRightLeft, ShieldAlert, ClipboardList, Send,
} from "lucide-react";

/**
 * Full stock workspace — extracted from the original dashboard/inventory/
 * page.tsx unmodified. Already self-gates correctly for every tier with
 * `inventory` access: write actions (add/receive/adjust, transfers, counts)
 * simply fail server-side with a 403 for read-only tiers, and the
 * variance-report panel already only renders when the backend actually
 * returns data (Controller/Manager/Owner) — a role without /stock/* access
 * (e.g. Kitchen's read-only view) gets a null response, not an error, so the
 * panel is silently absent rather than broken. Reused as-is by Owner and by
 * Stockkeeper (both have full inventory RW + transfer/count access per
 * directive 015) — Controller gets a separate, read-only VarianceReportPanel
 * instead of this whole workspace, since Controller has no write access here
 * at all.
 */
export default function InventoryWorkspace() {
    const [items, setItems] = useState<any[]>([]);
    const [aiData, setAiData] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [showAddForm, setShowAddForm] = useState(false);
    const [showReceiveForm, setShowReceiveForm] = useState<number | null>(null);
    const [showAdjustForm, setShowAdjustForm] = useState<number | null>(null);

    // Directive 016/017: store<->kitchen chain of custody (push + pull) +
    // variance report + physical counts. All best-effort — a role without
    // access to /stock/* (e.g. Waiter) simply doesn't see these panels
    // rather than the page erroring.
    const [transfers, setTransfers] = useState<any[] | null>(null);
    const [variance, setVariance] = useState<any | null>(null);
    const [showTransferForm, setShowTransferForm] = useState(false);
    const [transferItemId, setTransferItemId] = useState("");
    const [transferQty, setTransferQty] = useState("");
    const [confirmingId, setConfirmingId] = useState<number | null>(null);
    const [confirmQty, setConfirmQty] = useState("");

    // Kitchen requisition (pull) — directive 017
    const [showRequestForm, setShowRequestForm] = useState(false);
    const [requestItemId, setRequestItemId] = useState("");
    const [fulfillingId, setFulfillingId] = useState<number | null>(null);
    const [fulfillQty, setFulfillQty] = useState("");

    // Physical stock count — directive 017
    const [showCountForm, setShowCountForm] = useState(false);
    const [countItemId, setCountItemId] = useState("");
    const [countQty, setCountQty] = useState("");

    const [newName, setNewName] = useState("");
    const [newUnit, setNewUnit] = useState("kg");
    const [newQty, setNewQty] = useState("");
    const [newCost, setNewCost] = useState("");
    const [newThreshold, setNewThreshold] = useState("10");

    const [receiveQty, setReceiveQty] = useState("");
    const [receiveCost, setReceiveCost] = useState("");
    const [receiveSupplier, setReceiveSupplier] = useState("");

    const [adjustQty, setAdjustQty] = useState("");
    const [adjustReason, setAdjustReason] = useState("");

    const [submitting, setSubmitting] = useState(false);
    const [toast, setToast] = useState("");

    const fetchData = async () => {
        const [invRes, aiRes, transfersRes, varianceRes] = await Promise.all([
            api.get("/inventory/").catch(() => ({ data: [] })),
            api.get("/ai/inventory-predictions").catch(() => ({ data: null })),
            api.get("/stock/transfers").catch(() => null),
            api.get("/stock/variance-report").catch(() => null),
        ]);
        setItems(Array.isArray(invRes.data) ? invRes.data : []);
        setAiData(aiRes.data);
        // Only the still-actionable statuses belong in this compact panel —
        // confirmed/disputed history isn't shown here.
        setTransfers(
            transfersRes
                ? (transfersRes.data as any[]).filter((t) => t.status === "requested" || t.status === "pending")
                : null
        );
        setVariance(varianceRes ? varianceRes.data : null);
        setLoading(false);
    };

    useEffect(() => { fetchData(); }, []);

    const showToast = (msg: string) => {
        setToast(msg);
        setTimeout(() => setToast(""), 3000);
    };

    const handleAddItem = async () => {
        if (!newName) return;
        setSubmitting(true);
        try {
            await api.post("/inventory/", {
                item_name: newName,
                quantity: parseFloat(newQty) || 0,
                unit: newUnit,
                cost_per_unit: parseFloat(newCost) || 0,
                low_stock_threshold: parseInt(newThreshold) || 10,
            });
            showToast(`Added ${newName}`);
            setShowAddForm(false);
            setNewName(""); setNewQty(""); setNewCost("");
            await fetchData();
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to add item");
        }
        setSubmitting(false);
    };

    const handleReceive = async (itemId: number) => {
        if (!receiveQty) return;
        setSubmitting(true);
        try {
            const res = await api.post(`/inventory/${itemId}/receive`, {
                quantity: parseFloat(receiveQty),
                cost_per_unit: receiveCost ? parseFloat(receiveCost) : null,
                supplier: receiveSupplier,
            });
            showToast(res.data.message);
            setShowReceiveForm(null);
            setReceiveQty(""); setReceiveCost(""); setReceiveSupplier("");
            await fetchData();
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to record receipt");
        }
        setSubmitting(false);
    };

    const handleAdjust = async (itemId: number) => {
        if (!adjustQty) return;
        setSubmitting(true);
        try {
            const res = await api.post(`/inventory/${itemId}/adjust`, {
                quantity: -Math.abs(parseFloat(adjustQty)),
                reason: adjustReason,
            });
            showToast(res.data.message);
            setShowAdjustForm(null);
            setAdjustQty(""); setAdjustReason("");
            await fetchData();
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to record adjustment");
        }
        setSubmitting(false);
    };

    const handleInitiateTransfer = async () => {
        if (!transferItemId || !transferQty) return;
        setSubmitting(true);
        try {
            await api.post("/stock/transfers", {
                inventory_item_id: parseInt(transferItemId),
                quantity: parseFloat(transferQty),
                from_location: "store",
                to_location: "kitchen",
            });
            showToast("Transfer sent to kitchen for confirmation");
            setShowTransferForm(false);
            setTransferItemId(""); setTransferQty("");
            await fetchData();
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to start transfer");
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
                    ? "Recorded — quantity didn't match, flagged for review"
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

    const handleRequestStock = async () => {
        if (!requestItemId) return;
        setSubmitting(true);
        try {
            await api.post("/stock/transfers/request", {
                inventory_item_id: parseInt(requestItemId),
                from_location: "store",
                to_location: "kitchen",
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

    const handleFulfillTransfer = async (transferId: number) => {
        if (!fulfillQty) return;
        setSubmitting(true);
        try {
            await api.post(`/stock/transfers/${transferId}/fulfil`, {
                quantity: parseFloat(fulfillQty),
            });
            showToast("Marked as sent — awaiting confirmation");
            setFulfillingId(null);
            setFulfillQty("");
            await fetchData();
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to fulfil request");
        }
        setSubmitting(false);
    };

    const handleSubmitCount = async () => {
        if (!countItemId || !countQty) return;
        setSubmitting(true);
        try {
            const res = await api.post("/stock/counts", {
                inventory_item_id: parseInt(countItemId),
                counted_quantity: parseFloat(countQty),
            });
            const gap = res.data.counted_quantity - res.data.expected_quantity;
            showToast(Math.abs(gap) < 0.001 ? "Count matches — no adjustment needed" : `Count recorded, stock updated (${gap > 0 ? "+" : ""}${gap.toFixed(1)})`);
            setShowCountForm(false);
            setCountItemId(""); setCountQty("");
            await fetchData();
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to record count");
        }
        setSubmitting(false);
    };

    if (loading) {
        return (
            <div className="space-y-3">
                {[...Array(4)].map((_, i) => (
                    <div key={i} className="bg-[var(--surface)] rounded-xl h-14 animate-pulse" />
                ))}
            </div>
        );
    }

    const summary = aiData?.summary || {};
    const predictions = aiData?.predictions || [];
    const alerts = aiData?.alerts || [];

    // Demo stock alerts only in explicit demo mode; a real empty store shows
    // its own (empty) workspace with add controls, not Lavy's fake alerts.
    const isDemo = isDemoMode() && items.length === 0 && alerts.length === 0;
    const demoAlerts = demoData.stockAlerts;

    const priorityLabel = (c: string) => {
        const map: Record<string, string> = { A: "High use", B: "Medium", C: "Low use" };
        return map[c] || c;
    };
    const priorityColor = (c: string) => {
        const map: Record<string, string> = {
            A: "bg-[var(--success)]/10 text-[var(--success)]",
            B: "bg-[var(--warning)]/10 text-[var(--warning)]",
            C: "bg-[var(--text-muted)]/10 text-[var(--text-muted)]",
        };
        return map[c] || "bg-[var(--text-muted)]/10 text-[var(--text-muted)]";
    };

    const getPrediction = (name: string) => predictions.find((p: any) =>
        p.item_name?.toLowerCase() === name?.toLowerCase()
    );

    return (
        <div className="space-y-5">
            {/* Toast */}
            <AnimatePresence>
                {toast && (
                    <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}
                        className="fixed top-4 right-4 z-50 bg-[var(--success)]/10 border border-[var(--success)]/30 rounded-xl px-5 py-3 flex items-center gap-2">
                        <Check className="w-4 h-4 text-[var(--success)]" />
                        <span className="text-sm text-[var(--success)]">{toast}</span>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-xl font-bold text-[var(--text)]">Stock</h1>
                    <p className="text-sm text-[var(--text-dim)] mt-0.5">
                        {isDemo ? "Demo stock alerts" : `${items.length} item${items.length !== 1 ? "s" : ""} tracked from your store`}
                    </p>
                </div>
                <div className="flex gap-2">
                    <button onClick={() => setShowAddForm(!showAddForm)}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--accent)]/10 border border-[var(--accent)]/30 rounded-lg text-xs text-[var(--accent)] hover:bg-[var(--accent)]/20 transition-all">
                        <Plus className="w-3 h-3" />
                        Add Item
                    </button>
                </div>
            </div>

            {/* Demo Banner */}
            {isDemo && (
                <div className="flex items-center gap-2 px-3 py-1.5 bg-[var(--accent)]/8 border border-[var(--accent)]/20 rounded-lg">
                    <span className="text-[10px] text-[var(--accent)]">📊 Demo Mode — Showing sample data for Lavy restaurant</span>
                </div>
            )}

            {/* Add item form */}
            <AnimatePresence>
                {showAddForm && (
                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                        className="bg-[var(--surface)] border border-[var(--accent)]/20 rounded-xl overflow-hidden">
                        <div className="px-4 py-3 border-b border-[var(--surface-hover)] flex items-center justify-between">
                            <span className="text-xs font-semibold text-[var(--text)]">New Stock Item</span>
                            <button onClick={() => setShowAddForm(false)} aria-label="Close form"><X className="w-4 h-4 text-[var(--text-dim)]" /></button>
                        </div>
                        <div className="p-4 grid grid-cols-2 sm:grid-cols-5 gap-3">
                            <input placeholder="Item name" value={newName} onChange={(e) => setNewName(e.target.value)}
                                className="col-span-2 bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-3 py-2 text-xs text-[var(--text)] placeholder-[var(--text-dim)] focus:border-[var(--accent)]/50 focus:outline-none" />
                            <input placeholder="Quantity" value={newQty} onChange={(e) => setNewQty(e.target.value)} type="number"
                                className="bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-3 py-2 text-xs text-[var(--text)] placeholder-[var(--text-dim)] focus:border-[var(--accent)]/50 focus:outline-none" />
                            <select value={newUnit} onChange={(e) => setNewUnit(e.target.value)}
                                className="bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-3 py-2 text-xs text-[var(--text)] focus:border-[var(--accent)]/50 focus:outline-none">
                                <option value="kg">kg</option>
                                <option value="liters">liters</option>
                                <option value="pieces">pieces</option>
                                <option value="bags">bags</option>
                                <option value="crates">crates</option>
                                <option value="bottles">bottles</option>
                            </select>
                            <button onClick={handleAddItem} disabled={!newName || submitting}
                                className="bg-[var(--accent)] text-black rounded-lg px-3 py-2 text-xs font-semibold disabled:opacity-50">
                                {submitting ? "Adding..." : "Add"}
                            </button>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Demo: Stock Alerts with urgency colours */}
            {isDemo && (
                <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl">
                    <div className="px-4 py-3 border-b border-[var(--surface-hover)] flex items-center gap-2">
                        <AlertTriangle className="w-3.5 h-3.5 text-[var(--warning)]" />
                        <p className="text-xs font-semibold text-[var(--text)]">Stock Alerts</p>
                    </div>
                    <div className="divide-y divide-[var(--surface-hover)]">
                        {demoAlerts.map((alert, i) => {
                            const isUrgent = alert.urgency === "URGENT";
                            return (
                                <motion.div
                                    key={i}
                                    initial={{ opacity: 0, x: -8 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: i * 0.08 }}
                                    className="px-4 py-3 flex items-center gap-3"
                                >
                                    <div className={`w-2 h-2 rounded-full flex-shrink-0 ${isUrgent ? "bg-[var(--danger)] animate-pulse" : "bg-[var(--warning)]"}`} />
                                    <div className="flex-1">
                                        <div className="flex items-center gap-2">
                                            <p className="text-sm text-[var(--text)]">{alert.item}</p>
                                            <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded ${isUrgent
                                                ? "bg-[var(--danger)]/10 text-[var(--danger)]"
                                                : "bg-[var(--warning)]/10 text-[var(--warning)]"
                                                }`}>
                                                {alert.urgency}
                                            </span>
                                        </div>
                                        <p className="text-[10px] text-[var(--text-dim)] mt-0.5">
                                            {alert.quantity} remaining · ~{alert.hours_left}h left
                                        </p>
                                    </div>
                                    <span className={`text-xs font-semibold ${isUrgent ? "text-[var(--danger)]" : "text-[var(--warning)]"}`}>
                                        {isUrgent ? "Reorder now" : "Reorder soon"}
                                    </span>
                                </motion.div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* Real: AI overview */}
            {!isDemo && (summary.total_items > 0 || predictions.length > 0) && (
                <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl">
                    <div className="px-4 py-3 border-b border-[var(--surface-hover)]">
                        <p className="text-xs font-semibold text-[var(--text)]">Stock overview</p>
                    </div>
                    <div className="px-4 py-3 space-y-2">
                        {summary.critical_items > 0 && (
                            <p className="text-xs text-[var(--danger)]">
                                ⚠️ {summary.critical_items} item{summary.critical_items > 1 ? "s have" : " has"} run out — restock now
                            </p>
                        )}
                        {summary.low_stock_items > 0 && (
                            <p className="text-xs text-[var(--warning)]">
                                📦 {summary.low_stock_items} item{summary.low_stock_items > 1 ? "s are" : " is"} running low
                            </p>
                        )}
                        {summary.high_spoilage_items > 0 && (
                            <p className="text-xs text-[var(--text-muted)]">
                                🗑️ {summary.high_spoilage_items} item{summary.high_spoilage_items > 1 ? "s" : ""} might spoil soon
                            </p>
                        )}
                        {summary.monthly_spend > 0 && (
                            <p className="text-xs text-[var(--text-muted)]">
                                💰 Spending about KES {(summary.monthly_spend / 100).toLocaleString("en-KE")}/month on stock
                            </p>
                        )}
                    </div>
                </div>
            )}

            {/* Real: Stock items */}
            {!isDemo && (
                <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl">
                    <div className="px-4 py-3 border-b border-[var(--surface-hover)]">
                        <p className="text-xs font-semibold text-[var(--text)]">All items</p>
                    </div>
                    <div className="divide-y divide-[var(--surface-hover)]">
                        {items.length === 0 ? (
                            <p className="text-xs text-[var(--text-dim)] text-center py-8">No stock items yet — add your first one</p>
                        ) : (
                            items.map((item) => {
                                const pred = getPrediction(item.item_name);
                                const isLow = item.quantity <= item.low_stock_threshold;
                                const isOut = item.quantity <= 0;
                                const isReceiving = showReceiveForm === item.id;
                                const isAdjusting = showAdjustForm === item.id;

                                return (
                                    <div key={item.id} className="px-4 py-3">
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-3 flex-1">
                                                <div className={`w-2 h-2 rounded-full flex-shrink-0 ${isOut ? "bg-[var(--danger)]" : isLow ? "bg-[var(--warning)]" : "bg-[var(--success)]"}`} />
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2">
                                                        <p className="text-sm text-[var(--text)]">{item.item_name}</p>
                                                        {pred?.abc_class && (
                                                            <span className={`text-[9px] px-1.5 py-0.5 rounded ${priorityColor(pred.abc_class)}`}>
                                                                {priorityLabel(pred.abc_class)}
                                                            </span>
                                                        )}
                                                    </div>
                                                    <div className="flex items-center gap-3 mt-0.5">
                                                        <span className={`text-xs ${isLow ? "text-[var(--warning)]" : "text-[var(--text-muted)]"}`}>
                                                            {item.quantity} {item.unit}
                                                        </span>
                                                        {pred?.days_until_stockout != null && pred.days_until_stockout <= 14 && (
                                                            <span className="text-[10px] text-[var(--warning)]">
                                                                {pred.days_until_stockout <= 0 ? "Out of stock!" : `~${pred.days_until_stockout} days left`}
                                                            </span>
                                                        )}
                                                        {item.cost_per_unit > 0 && (
                                                            <span className="text-[10px] text-[var(--text-dim)]">
                                                                KES {item.cost_per_unit}/{item.unit}
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-1">
                                                <button onClick={() => { setShowReceiveForm(isReceiving ? null : item.id); setShowAdjustForm(null); }}
                                                    className={`text-[10px] px-2 py-1 rounded transition-all ${isReceiving ? "bg-[var(--success)]/10 text-[var(--success)]" : "bg-[var(--surface-hover)] text-[var(--text-muted)] hover:text-[var(--success)]"}`}>
                                                    <TruckIcon className="w-3 h-3 inline mr-0.5" />
                                                    Receive
                                                </button>
                                                <button onClick={() => { setShowAdjustForm(isAdjusting ? null : item.id); setShowReceiveForm(null); }}
                                                    className={`text-[10px] px-2 py-1 rounded transition-all ${isAdjusting ? "bg-[var(--danger)]/10 text-[var(--danger)]" : "bg-[var(--surface-hover)] text-[var(--text-muted)] hover:text-[var(--warning)]"}`}>
                                                    <Minus className="w-3 h-3 inline mr-0.5" />
                                                    Adjust
                                                </button>
                                            </div>
                                        </div>

                                        <AnimatePresence>
                                            {isReceiving && (
                                                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                                    className="mt-2 flex gap-2 items-center">
                                                    <input placeholder="Quantity" value={receiveQty} onChange={(e) => setReceiveQty(e.target.value)}
                                                        type="number" className="w-20 bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] placeholder-[var(--text-dim)] focus:outline-none" />
                                                    <input placeholder="Supplier (optional)" value={receiveSupplier} onChange={(e) => setReceiveSupplier(e.target.value)}
                                                        className="flex-1 bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] placeholder-[var(--text-dim)] focus:outline-none" />
                                                    <button onClick={() => handleReceive(item.id)} disabled={!receiveQty || submitting}
                                                        className="bg-[var(--success)] text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                                                        {submitting ? "..." : "Receive"}
                                                    </button>
                                                </motion.div>
                                            )}
                                        </AnimatePresence>

                                        <AnimatePresence>
                                            {isAdjusting && (
                                                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                                    className="mt-2 flex gap-2 items-center">
                                                    <input placeholder="Qty to remove" value={adjustQty} onChange={(e) => setAdjustQty(e.target.value)}
                                                        type="number" className="w-24 bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] placeholder-[var(--text-dim)] focus:outline-none" />
                                                    <select value={adjustReason} onChange={(e) => setAdjustReason(e.target.value)}
                                                        className="flex-1 bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] focus:outline-none">
                                                        <option value="">Reason</option>
                                                        <option value="waste">Waste / spoilage</option>
                                                        <option value="breakage">Breakage</option>
                                                        <option value="theft">Theft / loss</option>
                                                        <option value="correction">Correction</option>
                                                    </select>
                                                    <button onClick={() => handleAdjust(item.id)} disabled={!adjustQty || submitting}
                                                        className="bg-[var(--danger)] text-white rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                                                        {submitting ? "..." : "Remove"}
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
            )}

            {/* Store <-> kitchen transfers, both directions (directive 016
                push, directive 017 pull). Only shown to roles that can reach
                /stock/transfers — Waiter/Supervisor get null back and the
                panel doesn't render, rather than an error state. */}
            {transfers !== null && (
                <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl">
                    <div className="px-4 py-3 border-b border-[var(--surface-hover)] flex items-center justify-between flex-wrap gap-2">
                        <div className="flex items-center gap-2">
                            <ArrowRightLeft className="w-3.5 h-3.5 text-[var(--accent)]" />
                            <p className="text-xs font-semibold text-[var(--text)]">Store ↔ kitchen</p>
                        </div>
                        <div className="flex gap-2">
                            <button onClick={() => { setShowRequestForm(!showRequestForm); setShowTransferForm(false); }}
                                className="text-[10px] px-2 py-1 rounded bg-[var(--surface-hover)] text-[var(--text-muted)] hover:text-[var(--accent)] transition-all">
                                <ClipboardList className="w-3 h-3 inline mr-0.5" />
                                Request from store
                            </button>
                            <button onClick={() => { setShowTransferForm(!showTransferForm); setShowRequestForm(false); }}
                                className="text-[10px] px-2 py-1 rounded bg-[var(--surface-hover)] text-[var(--text-muted)] hover:text-[var(--accent)] transition-all">
                                <Send className="w-3 h-3 inline mr-0.5" />
                                Send to kitchen
                            </button>
                        </div>
                    </div>

                    <AnimatePresence>
                        {showRequestForm && (
                            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                className="px-4 py-3 border-b border-[var(--surface-hover)] flex gap-2 items-center overflow-hidden">
                                <select value={requestItemId} onChange={(e) => setRequestItemId(e.target.value)}
                                    className="flex-1 bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] focus:outline-none">
                                    <option value="">What do you need?</option>
                                    {items.map((i) => <option key={i.id} value={i.id}>{i.item_name}</option>)}
                                </select>
                                <button onClick={handleRequestStock} disabled={!requestItemId || submitting}
                                    className="bg-[var(--accent)] text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                                    {submitting ? "..." : "Request"}
                                </button>
                            </motion.div>
                        )}
                    </AnimatePresence>

                    <AnimatePresence>
                        {showTransferForm && (
                            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                className="px-4 py-3 border-b border-[var(--surface-hover)] flex gap-2 items-center overflow-hidden">
                                <select value={transferItemId} onChange={(e) => setTransferItemId(e.target.value)}
                                    className="flex-1 bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] focus:outline-none">
                                    <option value="">Select item…</option>
                                    {items.map((i) => <option key={i.id} value={i.id}>{i.item_name}</option>)}
                                </select>
                                <input placeholder="Quantity" value={transferQty} onChange={(e) => setTransferQty(e.target.value)}
                                    type="number" className="w-24 bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] placeholder-[var(--text-dim)] focus:outline-none" />
                                <button onClick={handleInitiateTransfer} disabled={!transferItemId || !transferQty || submitting}
                                    className="bg-[var(--accent)] text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                                    {submitting ? "..." : "Send"}
                                </button>
                            </motion.div>
                        )}
                    </AnimatePresence>

                    <div className="divide-y divide-[var(--surface-hover)]">
                        {transfers.length === 0 ? (
                            <p className="text-xs text-[var(--text-dim)] text-center py-6">Nothing pending</p>
                        ) : (
                            transfers.map((t) => {
                                const isRequested = t.status === "requested";
                                const isFulfilling = fulfillingId === t.id;
                                return (
                                    <div key={t.id} className="px-4 py-3">
                                        <div className="flex items-center justify-between">
                                            <div>
                                                <p className="text-sm text-[var(--text)]">
                                                    #{t.id} · {isRequested ? "requested" : `${t.quantity}${t.unit}`} {t.from_location} → {t.to_location}
                                                </p>
                                                <p className="text-[10px] text-[var(--text-dim)] mt-0.5">
                                                    {isRequested ? "Waiting for the store to send it" : "Awaiting confirmation from receiver"}
                                                </p>
                                            </div>
                                            {isRequested ? (
                                                <button
                                                    onClick={() => { setFulfillingId(isFulfilling ? null : t.id); setFulfillQty(""); }}
                                                    className="text-[10px] px-2 py-1 rounded bg-[var(--surface-hover)] text-[var(--text-muted)] hover:text-[var(--accent)] transition-all">
                                                    Fulfil
                                                </button>
                                            ) : (
                                                <button
                                                    onClick={() => { setConfirmingId(confirmingId === t.id ? null : t.id); setConfirmQty(String(t.quantity)); }}
                                                    className="text-[10px] px-2 py-1 rounded bg-[var(--surface-hover)] text-[var(--text-muted)] hover:text-[var(--success)] transition-all">
                                                    Confirm receipt
                                                </button>
                                            )}
                                        </div>
                                        <AnimatePresence>
                                            {isFulfilling && (
                                                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                                    className="mt-2 flex gap-2 items-center">
                                                    <input placeholder="Quantity being sent" value={fulfillQty} onChange={(e) => setFulfillQty(e.target.value)}
                                                        type="number" className="flex-1 bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] placeholder-[var(--text-dim)] focus:outline-none" />
                                                    <button onClick={() => handleFulfillTransfer(t.id)} disabled={!fulfillQty || submitting}
                                                        className="bg-[var(--accent)] text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                                                        {submitting ? "..." : "Send"}
                                                    </button>
                                                </motion.div>
                                            )}
                                        </AnimatePresence>
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
            )}

            {/* Physical stock count (directive 017) — the independent check
                that keeps theft/shrinkage detection meaningful once
                ingredient deduction is automatic. Shown whenever the
                transfers panel is (same role gate on the backend). */}
            {transfers !== null && (
                <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl">
                    <div className="px-4 py-3 border-b border-[var(--surface-hover)] flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <ClipboardList className="w-3.5 h-3.5 text-[var(--accent)]" />
                            <p className="text-xs font-semibold text-[var(--text)]">Physical count</p>
                        </div>
                        <button onClick={() => setShowCountForm(!showCountForm)}
                            className="text-[10px] px-2 py-1 rounded bg-[var(--surface-hover)] text-[var(--text-muted)] hover:text-[var(--accent)] transition-all">
                            <Plus className="w-3 h-3 inline mr-0.5" />
                            Count an item
                        </button>
                    </div>
                    <AnimatePresence>
                        {showCountForm && (
                            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                className="px-4 py-3 flex gap-2 items-center overflow-hidden">
                                <select value={countItemId} onChange={(e) => setCountItemId(e.target.value)}
                                    className="flex-1 bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] focus:outline-none">
                                    <option value="">What did you count?</option>
                                    {items.map((i) => <option key={i.id} value={i.id}>{i.item_name}</option>)}
                                </select>
                                <input placeholder="What's actually there" value={countQty} onChange={(e) => setCountQty(e.target.value)}
                                    type="number" className="w-32 bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] placeholder-[var(--text-dim)] focus:outline-none" />
                                <button onClick={handleSubmitCount} disabled={!countItemId || !countQty || submitting}
                                    className="bg-[var(--accent)] text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                                    {submitting ? "..." : "Record"}
                                </button>
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>
            )}

            {/* Variance report (directive 016) — Controller/Manager/Owner only,
                same null-means-hidden pattern as transfers above. */}
            {variance !== null && variance.items?.some((i: any) => i.flagged) && (
                <div className="bg-[var(--surface)] border border-[var(--danger)]/20 rounded-xl">
                    <div className="px-4 py-3 border-b border-[var(--surface-hover)] flex items-center gap-2">
                        <ShieldAlert className="w-3.5 h-3.5 text-[var(--danger)]" />
                        <p className="text-xs font-semibold text-[var(--text)]">
                            Stock variance — {variance.items.filter((i: any) => i.flagged).length} item(s) over {(variance.threshold * 100).toFixed(0)}%
                        </p>
                    </div>
                    <div className="divide-y divide-[var(--surface-hover)]">
                        {variance.items.filter((i: any) => i.flagged).map((i: any) => (
                            <div key={i.inventory_item_id} className="px-4 py-2.5 flex items-center justify-between">
                                <p className="text-xs text-[var(--text)]">{i.item_name}</p>
                                <p className="text-xs text-[var(--danger)]">
                                    {(i.variance_pct * 100).toFixed(1)}% (expected ~{i.theoretical_usage.toFixed(1)}, actual {i.actual_usage.toFixed(1)})
                                </p>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Real: AI alerts */}
            {!isDemo && alerts.length > 0 && (
                <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl">
                    <div className="px-4 py-3 border-b border-[var(--surface-hover)] flex items-center gap-2">
                        <AlertTriangle className="w-3.5 h-3.5 text-[var(--warning)]" />
                        <p className="text-xs font-semibold text-[var(--text)]">What to do</p>
                    </div>
                    <div className="divide-y divide-[var(--surface-hover)]">
                        {alerts.map((alert: any, i: number) => (
                            <div key={i} className="px-4 py-2.5">
                                <p className="text-xs text-[var(--text)]">{alert.message}</p>
                                {alert.action && (
                                    <p className="text-[10px] text-[var(--accent)] mt-0.5">→ {alert.action}</p>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
