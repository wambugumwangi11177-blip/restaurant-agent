"use client";

import { useState } from "react";
import api from "@/lib/api";
import { motion, AnimatePresence } from "framer-motion";
import { Plus, Pencil } from "lucide-react";
import FormField from "@/components/ui/FormField";
import type { ToastType } from "@/components/ui/Toast";
import { getErrorMessage } from "@/lib/errors";
import type { Supplier } from "./types";

interface SupplierPanelProps {
    suppliers: Supplier[] | null;
    submitting: boolean;
    setSubmitting: (v: boolean) => void;
    showToast: (message: string, type?: ToastType) => void;
    fetchAll: () => Promise<void>;
}

export default function SupplierPanel({ suppliers, submitting, setSubmitting, showToast, fetchAll }: SupplierPanelProps) {
    const [showSupplierForm, setShowSupplierForm] = useState(false);
    const [supplierName, setSupplierName] = useState("");
    const [supplierPhone, setSupplierPhone] = useState("");
    const [supplierLeadDays, setSupplierLeadDays] = useState("2");

    const [editingSupplierId, setEditingSupplierId] = useState<number | null>(null);
    const [editSupplier, setEditSupplier] = useState({ name: "", contact_phone: "", avg_lead_days: "", notes: "" });

    const handleAddSupplier = async () => {
        if (!supplierName) return;
        setSubmitting(true);
        try {
            await api.post("/suppliers/", {
                name: supplierName,
                contact_phone: supplierPhone || "",
                avg_lead_days: parseFloat(supplierLeadDays) || 1,
            });
            showToast(`Added ${supplierName}`);
            setShowSupplierForm(false);
            setSupplierName(""); setSupplierPhone(""); setSupplierLeadDays("2");
            await fetchAll();
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to add supplier"), "error");
        }
        setSubmitting(false);
    };

    const openEditSupplier = (s: Supplier) => {
        if (editingSupplierId === s.id) { setEditingSupplierId(null); return; }
        setEditingSupplierId(s.id);
        setEditSupplier({
            name: s.name,
            contact_phone: s.contact_phone || "",
            avg_lead_days: String(s.avg_lead_days ?? ""),
            notes: s.notes || "",
        });
    };

    const handleSaveSupplier = async (supplierId: number) => {
        setSubmitting(true);
        try {
            await api.put(`/suppliers/${supplierId}`, {
                name: editSupplier.name,
                contact_phone: editSupplier.contact_phone,
                avg_lead_days: editSupplier.avg_lead_days ? parseFloat(editSupplier.avg_lead_days) : undefined,
                notes: editSupplier.notes,
            });
            showToast("Supplier updated");
            setEditingSupplierId(null);
            await fetchAll();
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to update supplier"), "error");
        }
        setSubmitting(false);
    };

    return (
        <div className="bg-surface border border-border rounded-xl">
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
                <p className="text-xs font-semibold text-text">Suppliers</p>
                <button onClick={() => setShowSupplierForm(!showSupplierForm)}
                    className="text-[10px] px-2 py-1 rounded bg-surface-hover text-text-muted hover:text-accent transition-all">
                    <Plus className="w-3 h-3 inline mr-0.5" />
                    Add supplier
                </button>
            </div>
            <AnimatePresence>
                {showSupplierForm && (
                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                        className="px-4 py-3 border-b border-border flex gap-2 items-end flex-wrap overflow-hidden">
                        <FormField
                            label="Supplier name"
                            placeholder="Supplier name"
                            value={supplierName}
                            onChange={(e) => setSupplierName(e.target.value)}
                            className="flex-1 min-w-[140px] bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none" />
                        <FormField
                            label="Phone (for Twilio orders)"
                            placeholder="Phone (for Twilio orders)"
                            value={supplierPhone}
                            onChange={(e) => setSupplierPhone(e.target.value)}
                            className="flex-1 min-w-[160px] bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none" />
                        <FormField
                            label="Lead days"
                            placeholder="Lead days"
                            value={supplierLeadDays}
                            onChange={(e) => setSupplierLeadDays(e.target.value)}
                            type="number"
                            className="w-24 bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none" />
                        <button onClick={handleAddSupplier} disabled={!supplierName || submitting}
                            className="bg-accent text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                            {submitting ? "..." : "Add"}
                        </button>
                    </motion.div>
                )}
            </AnimatePresence>
            <div className="divide-y divide-border">
                {(suppliers || []).length === 0 ? (
                    <p className="text-xs text-text-dim text-center py-6">No suppliers yet</p>
                ) : (
                    (suppliers || []).map((s) => (
                        <div key={s.id} className="px-4 py-3">
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="text-sm text-text">{s.name}</p>
                                    <p className="text-[10px] text-text-dim mt-0.5">
                                        {s.contact_phone || "No phone on file"} · reliability {s.reliability_score != null ? `${s.reliability_score.toFixed(0)}%` : "n/a"}
                                    </p>
                                </div>
                                <button onClick={() => openEditSupplier(s)}
                                    className="text-[10px] px-2 py-1 rounded bg-surface-hover text-text-muted hover:text-accent transition-all flex items-center gap-1">
                                    <Pencil className="w-3 h-3" />
                                    {editingSupplierId === s.id ? "Close" : "Edit"}
                                </button>
                            </div>
                            <AnimatePresence>
                                {editingSupplierId === s.id && (
                                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                        className="mt-2 flex gap-2 items-end flex-wrap overflow-hidden">
                                        <FormField
                                            label="Name"
                                            placeholder="Name"
                                            value={editSupplier.name}
                                            onChange={(e) => setEditSupplier({ ...editSupplier, name: e.target.value })}
                                            className="flex-1 min-w-[140px] bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none" />
                                        <FormField
                                            label="Phone"
                                            placeholder="Phone"
                                            value={editSupplier.contact_phone}
                                            onChange={(e) => setEditSupplier({ ...editSupplier, contact_phone: e.target.value })}
                                            className="flex-1 min-w-[140px] bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none" />
                                        <FormField
                                            label="Lead days"
                                            placeholder="Lead days"
                                            value={editSupplier.avg_lead_days}
                                            type="number"
                                            onChange={(e) => setEditSupplier({ ...editSupplier, avg_lead_days: e.target.value })}
                                            className="w-24 bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none" />
                                        <FormField
                                            label="Notes"
                                            placeholder="Notes"
                                            value={editSupplier.notes}
                                            onChange={(e) => setEditSupplier({ ...editSupplier, notes: e.target.value })}
                                            className="flex-1 min-w-[140px] bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none" />
                                        <button onClick={() => handleSaveSupplier(s.id)} disabled={!editSupplier.name || submitting}
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
