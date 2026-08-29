"use client";

import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import FormField from "@/components/ui/FormField";

interface AddItemModalProps {
    show: boolean;
    onClose: () => void;
    newName: string;
    setNewName: (v: string) => void;
    newQty: string;
    setNewQty: (v: string) => void;
    newUnit: string;
    setNewUnit: (v: string) => void;
    submitting: boolean;
    onSubmit: () => void;
}

/**
 * "New Stock Item" form — extracted from InventoryWorkspace. Only
 * name/quantity/unit are user-editable here (cost_per_unit and
 * low_stock_threshold keep their defaults, matching the original
 * behaviour — no new fields were added).
 */
export default function AddItemModal({
    show,
    onClose,
    newName,
    setNewName,
    newQty,
    setNewQty,
    newUnit,
    setNewUnit,
    submitting,
    onSubmit,
}: AddItemModalProps) {
    return (
        <AnimatePresence>
            {show && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                    className="bg-surface border border-accent/20 rounded-xl overflow-hidden">
                    <div className="px-4 py-3 border-b border-surface-hover flex items-center justify-between">
                        <span className="text-xs font-semibold text-text">New Stock Item</span>
                        <button onClick={onClose} aria-label="Close form"><X className="w-4 h-4 text-text-dim" /></button>
                    </div>
                    <div className="p-4 grid grid-cols-2 sm:grid-cols-5 gap-3">
                        <FormField
                            label="Item name"
                            placeholder="Item name"
                            value={newName}
                            onChange={(e) => setNewName(e.target.value)}
                            className="col-span-2 bg-surface-hover border border-border rounded-lg px-3 py-2 text-xs text-text placeholder-text-dim focus:border-accent/50 focus:outline-none"
                        />
                        <FormField
                            label="Quantity"
                            placeholder="Quantity"
                            value={newQty}
                            onChange={(e) => setNewQty(e.target.value)}
                            type="number"
                            className="bg-surface-hover border border-border rounded-lg px-3 py-2 text-xs text-text placeholder-text-dim focus:border-accent/50 focus:outline-none"
                        />
                        <div className="flex flex-col gap-1">
                            <label htmlFor="new-item-unit" className="text-xs text-text-dim">Unit</label>
                            <select id="new-item-unit" value={newUnit} onChange={(e) => setNewUnit(e.target.value)}
                                className="bg-surface-hover border border-border rounded-lg px-3 py-2 text-xs text-text focus:border-accent/50 focus:outline-none">
                                <option value="kg">kg</option>
                                <option value="liters">liters</option>
                                <option value="pieces">pieces</option>
                                <option value="bags">bags</option>
                                <option value="crates">crates</option>
                                <option value="bottles">bottles</option>
                            </select>
                        </div>
                        <button onClick={onSubmit} disabled={!newName || submitting}
                            className="bg-accent text-black rounded-lg px-3 py-2 text-xs font-semibold disabled:opacity-50">
                            {submitting ? "Adding..." : "Add"}
                        </button>
                    </div>
                </motion.div>
            )}
        </AnimatePresence>
    );
}
