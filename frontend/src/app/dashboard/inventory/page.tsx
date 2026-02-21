"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { motion, AnimatePresence } from "framer-motion";
import {
    Package,
    AlertTriangle,
    Plus,
    TruckIcon,
    Minus,
    X,
    Check,
} from "lucide-react";

export default function InventoryPage() {
    const [items, setItems] = useState<any[]>([]);
    const [aiData, setAiData] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [showAddForm, setShowAddForm] = useState(false);
    const [showReceiveForm, setShowReceiveForm] = useState<number | null>(null);
    const [showAdjustForm, setShowAdjustForm] = useState<number | null>(null);

    // Add form
    const [newName, setNewName] = useState("");
    const [newUnit, setNewUnit] = useState("kg");
    const [newQty, setNewQty] = useState("");
    const [newCost, setNewCost] = useState("");
    const [newThreshold, setNewThreshold] = useState("10");

    // Receive form
    const [receiveQty, setReceiveQty] = useState("");
    const [receiveCost, setReceiveCost] = useState("");
    const [receiveSupplier, setReceiveSupplier] = useState("");

    // Adjust form
    const [adjustQty, setAdjustQty] = useState("");
    const [adjustReason, setAdjustReason] = useState("");

    const [submitting, setSubmitting] = useState(false);
    const [toast, setToast] = useState("");

    const fetchData = async () => {
        const [invRes, aiRes] = await Promise.all([
            api.get("/inventory/").catch(() => ({ data: [] })),
            api.get("/ai/inventory-predictions").catch(() => ({ data: null })),
        ]);
        setItems(Array.isArray(invRes.data) ? invRes.data : []);
        setAiData(aiRes.data);
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
        } catch (err) { console.error(err); }
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
        } catch (err) { console.error(err); }
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
        } catch (err) { console.error(err); }
        setSubmitting(false);
    };

    if (loading) {
        return (
            <div className="space-y-3">
                {[...Array(4)].map((_, i) => (
                    <div key={i} className="bg-[#141414] rounded-xl h-14 animate-pulse" />
                ))}
            </div>
        );
    }

    const summary = aiData?.summary || {};
    const predictions = aiData?.predictions || [];
    const alerts = aiData?.alerts || [];

    const priorityLabel = (c: string) => {
        const map: Record<string, string> = { A: "High use", B: "Medium", C: "Low use" };
        return map[c] || c;
    };
    const priorityColor = (c: string) => {
        const map: Record<string, string> = {
            A: "bg-[#22c55e]/10 text-[#22c55e]",
            B: "bg-[#eab308]/10 text-[#eab308]",
            C: "bg-[#737373]/10 text-[#737373]",
        };
        return map[c] || "bg-[#737373]/10 text-[#737373]";
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
                        className="fixed top-4 right-4 z-50 bg-[#22c55e]/10 border border-[#22c55e]/30 rounded-xl px-5 py-3 flex items-center gap-2">
                        <Check className="w-4 h-4 text-[#22c55e]" />
                        <span className="text-sm text-[#22c55e]">{toast}</span>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-xl font-bold text-[#e5e5e5]">Stock</h1>
                    <p className="text-sm text-[#525252] mt-0.5">
                        {items.length} item{items.length !== 1 ? "s" : ""} tracked from your store
                    </p>
                </div>
                <div className="flex gap-2">
                    <button onClick={() => setShowAddForm(!showAddForm)}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-[#d4a853]/10 border border-[#d4a853]/30 rounded-lg text-xs text-[#d4a853] hover:bg-[#d4a853]/20 transition-all">
                        <Plus className="w-3 h-3" />
                        Add Item
                    </button>
                </div>
            </div>

            {/* Add item form */}
            <AnimatePresence>
                {showAddForm && (
                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                        className="bg-[#141414] border border-[#d4a853]/20 rounded-xl overflow-hidden">
                        <div className="px-4 py-3 border-b border-[#1a1a1a] flex items-center justify-between">
                            <span className="text-xs font-semibold text-[#e5e5e5]">New Stock Item</span>
                            <button onClick={() => setShowAddForm(false)}><X className="w-4 h-4 text-[#525252]" /></button>
                        </div>
                        <div className="p-4 grid grid-cols-2 sm:grid-cols-5 gap-3">
                            <input placeholder="Item name" value={newName} onChange={(e) => setNewName(e.target.value)}
                                className="col-span-2 bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[#d4a853]/50 focus:outline-none" />
                            <input placeholder="Quantity" value={newQty} onChange={(e) => setNewQty(e.target.value)} type="number"
                                className="bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[#d4a853]/50 focus:outline-none" />
                            <select value={newUnit} onChange={(e) => setNewUnit(e.target.value)}
                                className="bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] focus:border-[#d4a853]/50 focus:outline-none">
                                <option value="kg">kg</option>
                                <option value="liters">liters</option>
                                <option value="pieces">pieces</option>
                                <option value="bags">bags</option>
                                <option value="crates">crates</option>
                                <option value="bottles">bottles</option>
                            </select>
                            <button onClick={handleAddItem} disabled={!newName || submitting}
                                className="bg-[#d4a853] text-black rounded-lg px-3 py-2 text-xs font-semibold disabled:opacity-50">
                                {submitting ? "Adding..." : "Add"}
                            </button>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* AI overview */}
            {(summary.total_items > 0 || predictions.length > 0) && (
                <div className="bg-[#141414] border border-[#262626] rounded-xl">
                    <div className="px-4 py-3 border-b border-[#1a1a1a]">
                        <p className="text-xs font-semibold text-[#e5e5e5]">Stock overview</p>
                    </div>
                    <div className="px-4 py-3 space-y-2">
                        {summary.critical_items > 0 && (
                            <p className="text-xs text-[#ef4444]">
                                ⚠️ {summary.critical_items} item{summary.critical_items > 1 ? "s have" : " has"} run out — restock now
                            </p>
                        )}
                        {summary.low_stock_items > 0 && (
                            <p className="text-xs text-[#eab308]">
                                📦 {summary.low_stock_items} item{summary.low_stock_items > 1 ? "s are" : " is"} running low
                            </p>
                        )}
                        {summary.high_spoilage_items > 0 && (
                            <p className="text-xs text-[#737373]">
                                🗑️ {summary.high_spoilage_items} item{summary.high_spoilage_items > 1 ? "s" : ""} might spoil soon
                            </p>
                        )}
                        {summary.monthly_spend > 0 && (
                            <p className="text-xs text-[#737373]">
                                💰 Spending about KES {(summary.monthly_spend / 100).toLocaleString("en-KE")}/month on stock
                            </p>
                        )}
                    </div>
                </div>
            )}

            {/* Stock items */}
            <div className="bg-[#141414] border border-[#262626] rounded-xl">
                <div className="px-4 py-3 border-b border-[#1a1a1a]">
                    <p className="text-xs font-semibold text-[#e5e5e5]">All items</p>
                </div>
                <div className="divide-y divide-[#1a1a1a]">
                    {items.length === 0 ? (
                        <p className="text-xs text-[#525252] text-center py-8">No stock items yet — add your first one</p>
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
                                            <div className={`w-2 h-2 rounded-full flex-shrink-0 ${isOut ? "bg-[#ef4444]" : isLow ? "bg-[#eab308]" : "bg-[#22c55e]"
                                                }`} />
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2">
                                                    <p className="text-sm text-[#e5e5e5]">{item.item_name}</p>
                                                    {pred?.abc_class && (
                                                        <span className={`text-[9px] px-1.5 py-0.5 rounded ${priorityColor(pred.abc_class)}`}>
                                                            {priorityLabel(pred.abc_class)}
                                                        </span>
                                                    )}
                                                </div>
                                                <div className="flex items-center gap-3 mt-0.5">
                                                    <span className={`text-xs ${isLow ? "text-[#eab308]" : "text-[#737373]"}`}>
                                                        {item.quantity} {item.unit}
                                                    </span>
                                                    {pred?.days_until_stockout != null && pred.days_until_stockout <= 14 && (
                                                        <span className="text-[10px] text-[#eab308]">
                                                            {pred.days_until_stockout <= 0 ? "Out of stock!" : `~${pred.days_until_stockout} days left`}
                                                        </span>
                                                    )}
                                                    {item.cost_per_unit > 0 && (
                                                        <span className="text-[10px] text-[#525252]">
                                                            KES {item.cost_per_unit}/{item.unit}
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-1">
                                            <button onClick={() => { setShowReceiveForm(isReceiving ? null : item.id); setShowAdjustForm(null); }}
                                                className={`text-[10px] px-2 py-1 rounded transition-all ${isReceiving ? "bg-[#22c55e]/10 text-[#22c55e]" : "bg-[#1a1a1a] text-[#737373] hover:text-[#22c55e]"
                                                    }`}>
                                                <TruckIcon className="w-3 h-3 inline mr-0.5" />
                                                Receive
                                            </button>
                                            <button onClick={() => { setShowAdjustForm(isAdjusting ? null : item.id); setShowReceiveForm(null); }}
                                                className={`text-[10px] px-2 py-1 rounded transition-all ${isAdjusting ? "bg-[#ef4444]/10 text-[#ef4444]" : "bg-[#1a1a1a] text-[#737373] hover:text-[#eab308]"
                                                    }`}>
                                                <Minus className="w-3 h-3 inline mr-0.5" />
                                                Adjust
                                            </button>
                                        </div>
                                    </div>

                                    {/* Receive stock form */}
                                    <AnimatePresence>
                                        {isReceiving && (
                                            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                                className="mt-2 flex gap-2 items-center">
                                                <input placeholder="Quantity" value={receiveQty} onChange={(e) => setReceiveQty(e.target.value)}
                                                    type="number" className="w-20 bg-[#1a1a1a] border border-[#262626] rounded-lg px-2 py-1.5 text-xs text-[#e5e5e5] placeholder-[#525252] focus:outline-none" />
                                                <input placeholder="Supplier (optional)" value={receiveSupplier} onChange={(e) => setReceiveSupplier(e.target.value)}
                                                    className="flex-1 bg-[#1a1a1a] border border-[#262626] rounded-lg px-2 py-1.5 text-xs text-[#e5e5e5] placeholder-[#525252] focus:outline-none" />
                                                <button onClick={() => handleReceive(item.id)} disabled={!receiveQty || submitting}
                                                    className="bg-[#22c55e] text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                                                    {submitting ? "..." : "Receive"}
                                                </button>
                                            </motion.div>
                                        )}
                                    </AnimatePresence>

                                    {/* Adjust stock form */}
                                    <AnimatePresence>
                                        {isAdjusting && (
                                            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                                className="mt-2 flex gap-2 items-center">
                                                <input placeholder="Qty to remove" value={adjustQty} onChange={(e) => setAdjustQty(e.target.value)}
                                                    type="number" className="w-24 bg-[#1a1a1a] border border-[#262626] rounded-lg px-2 py-1.5 text-xs text-[#e5e5e5] placeholder-[#525252] focus:outline-none" />
                                                <select value={adjustReason} onChange={(e) => setAdjustReason(e.target.value)}
                                                    className="flex-1 bg-[#1a1a1a] border border-[#262626] rounded-lg px-2 py-1.5 text-xs text-[#e5e5e5] focus:outline-none">
                                                    <option value="">Reason</option>
                                                    <option value="waste">Waste / spoilage</option>
                                                    <option value="breakage">Breakage</option>
                                                    <option value="theft">Theft / loss</option>
                                                    <option value="correction">Correction</option>
                                                </select>
                                                <button onClick={() => handleAdjust(item.id)} disabled={!adjustQty || submitting}
                                                    className="bg-[#ef4444] text-white rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
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

            {/* AI alerts */}
            {alerts.length > 0 && (
                <div className="bg-[#141414] border border-[#262626] rounded-xl">
                    <div className="px-4 py-3 border-b border-[#1a1a1a] flex items-center gap-2">
                        <AlertTriangle className="w-3.5 h-3.5 text-[#eab308]" />
                        <p className="text-xs font-semibold text-[#e5e5e5]">What to do</p>
                    </div>
                    <div className="divide-y divide-[#1a1a1a]">
                        {alerts.map((alert: any, i: number) => (
                            <div key={i} className="px-4 py-2.5">
                                <p className="text-xs text-[#e5e5e5]">{alert.message}</p>
                                {alert.action && (
                                    <p className="text-[10px] text-[#d4a853] mt-0.5">→ {alert.action}</p>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
