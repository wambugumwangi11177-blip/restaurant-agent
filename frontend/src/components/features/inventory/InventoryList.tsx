"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Minus, TruckIcon } from "lucide-react";
import FormField from "@/components/ui/FormField";
import type { InventoryItem, InventoryPrediction } from "./types";

const priorityLabel = (c: string) => {
    const map: Record<string, string> = { A: "High use", B: "Medium", C: "Low use" };
    return map[c] || c;
};
const priorityColor = (c: string) => {
    const map: Record<string, string> = {
        A: "bg-success/10 text-success",
        B: "bg-warning/10 text-warning",
        C: "bg-text-muted/10 text-text-muted",
    };
    return map[c] || "bg-text-muted/10 text-text-muted";
};

interface InventoryListProps {
    items: InventoryItem[];
    predictions: InventoryPrediction[];
    showReceiveForm: number | null;
    setShowReceiveForm: (id: number | null) => void;
    showAdjustForm: number | null;
    setShowAdjustForm: (id: number | null) => void;
    receiveQty: string;
    setReceiveQty: (v: string) => void;
    receiveSupplier: string;
    setReceiveSupplier: (v: string) => void;
    adjustQty: string;
    setAdjustQty: (v: string) => void;
    adjustReason: string;
    setAdjustReason: (v: string) => void;
    submitting: boolean;
    onReceive: (itemId: number) => void;
    onAdjust: (itemId: number) => void;
}

/**
 * "All items" panel — item listing plus the two per-item stock-correction
 * forms (receive / adjust) that expand inline below a row. Extracted from
 * InventoryWorkspace; behavior unchanged.
 */
export default function InventoryList({
    items,
    predictions,
    showReceiveForm,
    setShowReceiveForm,
    showAdjustForm,
    setShowAdjustForm,
    receiveQty,
    setReceiveQty,
    receiveSupplier,
    setReceiveSupplier,
    adjustQty,
    setAdjustQty,
    adjustReason,
    setAdjustReason,
    submitting,
    onReceive,
    onAdjust,
}: InventoryListProps) {
    const getPrediction = (name: string) => predictions.find((p) =>
        p.item_name?.toLowerCase() === name?.toLowerCase()
    );

    return (
        <div className="bg-surface border border-border rounded-xl">
            <div className="px-4 py-3 border-b border-surface-hover">
                <p className="text-xs font-semibold text-text">All items</p>
            </div>
            <div className="divide-y divide-surface-hover">
                {items.length === 0 ? (
                    <p className="text-xs text-text-dim text-center py-8">No stock items yet — add your first one</p>
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
                                        <div className={`w-2 h-2 rounded-full flex-shrink-0 ${isOut ? "bg-danger" : isLow ? "bg-warning" : "bg-success"}`} />
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2">
                                                <p className="text-sm text-text">{item.item_name}</p>
                                                {pred?.abc_class && (
                                                    <span className={`text-[9px] px-1.5 py-0.5 rounded ${priorityColor(pred.abc_class)}`}>
                                                        {priorityLabel(pred.abc_class)}
                                                    </span>
                                                )}
                                            </div>
                                            <div className="flex items-center gap-3 mt-0.5">
                                                <span className={`text-xs ${isLow ? "text-warning" : "text-text-muted"}`}>
                                                    {item.quantity} {item.unit}
                                                </span>
                                                {pred?.days_until_stockout != null && pred.days_until_stockout <= 14 && (
                                                    <span className="text-[10px] text-warning">
                                                        {pred.days_until_stockout <= 0 ? "Out of stock!" : `~${pred.days_until_stockout} days left`}
                                                    </span>
                                                )}
                                                {item.cost_per_unit > 0 && (
                                                    <span className="text-[10px] text-text-dim">
                                                        KES {item.cost_per_unit}/{item.unit}
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-1">
                                        <button onClick={() => { setShowReceiveForm(isReceiving ? null : item.id); setShowAdjustForm(null); }}
                                            className={`text-[10px] px-2 py-1 rounded transition-all ${isReceiving ? "bg-success/10 text-success" : "bg-surface-hover text-text-muted hover:text-success"}`}>
                                            <TruckIcon className="w-3 h-3 inline mr-0.5" />
                                            Receive
                                        </button>
                                        <button onClick={() => { setShowAdjustForm(isAdjusting ? null : item.id); setShowReceiveForm(null); }}
                                            className={`text-[10px] px-2 py-1 rounded transition-all ${isAdjusting ? "bg-danger/10 text-danger" : "bg-surface-hover text-text-muted hover:text-warning"}`}>
                                            <Minus className="w-3 h-3 inline mr-0.5" />
                                            Adjust
                                        </button>
                                    </div>
                                </div>

                                <AnimatePresence>
                                    {isReceiving && (
                                        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                            className="mt-2 flex gap-2 items-end">
                                            <FormField
                                                label="Quantity"
                                                placeholder="Quantity"
                                                value={receiveQty}
                                                onChange={(e) => setReceiveQty(e.target.value)}
                                                type="number"
                                                className="w-20 bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none"
                                            />
                                            <FormField
                                                label="Supplier (optional)"
                                                placeholder="Supplier (optional)"
                                                value={receiveSupplier}
                                                onChange={(e) => setReceiveSupplier(e.target.value)}
                                                className="flex-1 bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none"
                                            />
                                            <button onClick={() => onReceive(item.id)} disabled={!receiveQty || submitting}
                                                className="bg-success text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                                                {submitting ? "..." : "Receive"}
                                            </button>
                                        </motion.div>
                                    )}
                                </AnimatePresence>

                                <AnimatePresence>
                                    {isAdjusting && (
                                        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                            className="mt-2 flex gap-2 items-end">
                                            <FormField
                                                label="Qty to remove"
                                                placeholder="Qty to remove"
                                                value={adjustQty}
                                                onChange={(e) => setAdjustQty(e.target.value)}
                                                type="number"
                                                className="w-24 bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none"
                                            />
                                            <div className="flex-1 flex flex-col gap-1">
                                                <label htmlFor={`adjust-reason-${item.id}`} className="text-xs text-text-dim">Reason</label>
                                                <select id={`adjust-reason-${item.id}`} value={adjustReason} onChange={(e) => setAdjustReason(e.target.value)}
                                                    className="w-full bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text focus:outline-none">
                                                    <option value="">Reason</option>
                                                    <option value="waste">Waste / spoilage</option>
                                                    <option value="breakage">Breakage</option>
                                                    <option value="theft">Theft / loss</option>
                                                    <option value="correction">Correction</option>
                                                </select>
                                            </div>
                                            <button onClick={() => onAdjust(item.id)} disabled={!adjustQty || submitting}
                                                className="bg-danger text-white rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
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
    );
}
