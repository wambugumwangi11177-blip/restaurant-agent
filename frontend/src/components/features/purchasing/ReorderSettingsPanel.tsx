"use client";

import { useId, useState } from "react";
import api from "@/lib/api";
import { motion, AnimatePresence } from "framer-motion";
import { Settings2 } from "lucide-react";
import FormField from "@/components/ui/FormField";
import type { ToastType } from "@/components/ui/Toast";
import { getErrorMessage } from "@/lib/errors";
import type { PurchasingItem, Supplier } from "./types";

interface ReorderSettingsPanelProps {
    items: PurchasingItem[];
    suppliers: Supplier[] | null;
    submitting: boolean;
    setSubmitting: (v: boolean) => void;
    showToast: (message: string, type?: ToastType) => void;
    fetchAll: () => Promise<void>;
}

export default function ReorderSettingsPanel({ items, suppliers, submitting, setSubmitting, showToast, fetchAll }: ReorderSettingsPanelProps) {
    const [settingsOpenId, setSettingsOpenId] = useState<number | null>(null);
    const [parLevel, setParLevel] = useState("");
    const [defaultSupplierId, setDefaultSupplierId] = useState("");
    const supplierSelectId = useId();

    const openSettings = (item: PurchasingItem) => {
        if (settingsOpenId === item.id) { setSettingsOpenId(null); return; }
        setSettingsOpenId(item.id);
        setParLevel(item.par_level != null ? String(item.par_level) : "");
        setDefaultSupplierId(item.default_supplier_id != null ? String(item.default_supplier_id) : "");
    };

    const handleSaveSettings = async (itemId: number) => {
        setSubmitting(true);
        try {
            await api.put(`/inventory/${itemId}/reorder-settings`, {
                par_level: parLevel ? parseFloat(parLevel) : null,
                default_supplier_id: defaultSupplierId ? parseInt(defaultSupplierId) : null,
            });
            showToast("Reorder settings saved");
            setSettingsOpenId(null);
            await fetchAll();
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to save settings"), "error");
        }
        setSubmitting(false);
    };

    return (
        <div className="bg-surface border border-border rounded-xl">
            <div className="px-4 py-3 border-b border-border flex items-center gap-2">
                <Settings2 className="w-3.5 h-3.5 text-accent" />
                <p className="text-xs font-semibold text-text">Reorder settings</p>
            </div>
            <div className="divide-y divide-border">
                {items.length === 0 ? (
                    <p className="text-xs text-text-dim text-center py-6">No stock items yet</p>
                ) : (
                    items.map((item) => (
                        <div key={item.id} className="px-4 py-3">
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="text-sm text-text">{item.item_name}</p>
                                    <p className="text-[10px] text-text-dim mt-0.5">
                                        {item.par_level != null
                                            ? `Par level ${item.par_level}${item.unit}${item.default_supplier_id ? "" : " · no default supplier"}`
                                            : "Not set up for auto-reorder"}
                                    </p>
                                </div>
                                <button onClick={() => openSettings(item)}
                                    className="text-[10px] px-2 py-1 rounded bg-surface-hover text-text-muted hover:text-accent transition-all">
                                    {settingsOpenId === item.id ? "Close" : "Configure"}
                                </button>
                            </div>
                            <AnimatePresence>
                                {settingsOpenId === item.id && (
                                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                        className="mt-2 flex gap-2 items-center flex-wrap">
                                        <FormField
                                            label="Par level (target to restock to)"
                                            srOnlyLabel
                                            placeholder="Par level (target to restock to)"
                                            value={parLevel}
                                            onChange={(e) => setParLevel(e.target.value)}
                                            type="number"
                                            className="flex-1 min-w-[160px] bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none" />
                                        <div className="flex-1 min-w-[140px] flex flex-col gap-1">
                                            <label htmlFor={`${supplierSelectId}-${item.id}`} className="sr-only">Default supplier</label>
                                            <select id={`${supplierSelectId}-${item.id}`} value={defaultSupplierId} onChange={(e) => setDefaultSupplierId(e.target.value)}
                                                className="w-full bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text focus:outline-none">
                                                <option value="">No default supplier</option>
                                                {(suppliers || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                                            </select>
                                        </div>
                                        <button onClick={() => handleSaveSettings(item.id)} disabled={submitting}
                                            className="bg-accent text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                                            {submitting ? "..." : "Save"}
                                        </button>
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </div>
                    ))
                )}
            </div>
        </div>
    );
}
