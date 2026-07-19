"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { motion, AnimatePresence } from "framer-motion";
import { Truck, Plus, Check, ShieldAlert, Settings2, Pencil } from "lucide-react";

/**
 * Purchasing/supplier workspace — extracted from the original
 * dashboard/purchasing/page.tsx unmodified. Already self-gates: the backend
 * differentiates approve (Manager/Supervisor) vs receive (Manager/
 * Stockkeeper) vs read (Manager/Controller/Stockkeeper/Supervisor/Owner), and
 * a role outside all of those gets the existing 403 -> "forbidden" screen.
 * Reused as-is across every tier with `purchasing` access.
 */
export default function PurchasingWorkspace() {
    const [suppliers, setSuppliers] = useState<any[] | null>(null);
    const [items, setItems] = useState<any[]>([]);
    const [orders, setOrders] = useState<any[] | null>(null);
    const [loading, setLoading] = useState(true);
    const [forbidden, setForbidden] = useState(false);
    const [toast, setToast] = useState("");
    const [submitting, setSubmitting] = useState(false);

    const [showSupplierForm, setShowSupplierForm] = useState(false);
    const [supplierName, setSupplierName] = useState("");
    const [supplierPhone, setSupplierPhone] = useState("");
    const [supplierLeadDays, setSupplierLeadDays] = useState("2");

    const [settingsOpenId, setSettingsOpenId] = useState<number | null>(null);
    const [parLevel, setParLevel] = useState("");
    const [defaultSupplierId, setDefaultSupplierId] = useState("");

    const [receivingId, setReceivingId] = useState<number | null>(null);
    const [receiveQty, setReceiveQty] = useState("");

    const [editingSupplierId, setEditingSupplierId] = useState<number | null>(null);
    const [editSupplier, setEditSupplier] = useState({ name: "", contact_phone: "", avg_lead_days: "", notes: "" });

    const showToast = (msg: string) => {
        setToast(msg);
        setTimeout(() => setToast(""), 3000);
    };

    const fetchAll = async () => {
        try {
            const [suppliersRes, itemsRes, ordersRes] = await Promise.all([
                api.get("/suppliers/"),
                api.get("/inventory/"),
                api.get("/purchase-orders/"),
            ]);
            setSuppliers(suppliersRes.data);
            setItems(Array.isArray(itemsRes.data) ? itemsRes.data : []);
            setOrders(ordersRes.data);
            setForbidden(false);
        } catch (err: any) {
            if (err?.response?.status === 403) setForbidden(true);
        }
        setLoading(false);
    };

    useEffect(() => { fetchAll(); }, []);

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
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to add supplier");
        }
        setSubmitting(false);
    };

    const openSettings = (item: any) => {
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
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to save settings");
        }
        setSubmitting(false);
    };

    const openEditSupplier = (s: any) => {
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
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to update supplier");
        }
        setSubmitting(false);
    };

    const handleApprove = async (poId: number) => {
        setSubmitting(true);
        try {
            await api.post(`/purchase-orders/${poId}/approve`);
            showToast("Approved and sent to supplier");
            await fetchAll();
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to approve");
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
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to record delivery");
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

    if (forbidden) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[40vh] space-y-3 text-center">
                <ShieldAlert className="w-8 h-8 text-[var(--text-dim)]" />
                <p className="text-sm text-[var(--text-muted)]">
                    Purchasing is only available to Owners, Managers, Controllers, Supervisors, and Stockkeepers.
                </p>
            </div>
        );
    }

    const pendingOrders = (orders || []).filter((o) => o.status === "PENDING");
    const sentOrders = (orders || []).filter((o) => o.status === "SENT");
    const pastOrders = (orders || []).filter((o) => !["PENDING", "SENT"].includes(o.status));

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
                <h1 className="text-xl font-bold text-[var(--text)]">Purchasing</h1>
                <p className="text-sm text-[var(--text-dim)] mt-0.5">
                    Automated reordering — draft orders are prepared for you; nothing reaches a supplier without approval.
                </p>
            </div>

            {/* Purchase orders needing approval */}
            {pendingOrders.length > 0 && (
                <div className="bg-[var(--surface)] border border-[var(--accent)]/20 rounded-xl">
                    <div className="px-4 py-3 border-b border-[var(--border)] flex items-center gap-2">
                        <Truck className="w-3.5 h-3.5 text-[var(--accent)]" />
                        <p className="text-xs font-semibold text-[var(--text)]">Awaiting your approval</p>
                    </div>
                    <div className="divide-y divide-[var(--border)]">
                        {pendingOrders.map((po) => (
                            <div key={po.id} className="px-4 py-3 flex items-center justify-between">
                                <div>
                                    <p className="text-sm text-[var(--text)]">
                                        #{po.id} · {po.quantity_ordered}{po.unit} {po.item_name} from {po.supplier_name}
                                    </p>
                                    <p className="text-[10px] text-[var(--text-dim)] mt-0.5">{po.notes}</p>
                                </div>
                                <button onClick={() => handleApprove(po.id)} disabled={submitting}
                                    className="bg-[var(--accent)] text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50 whitespace-nowrap">
                                    {submitting ? "..." : "Approve & Send"}
                                </button>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Sent, awaiting delivery */}
            {sentOrders.length > 0 && (
                <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl">
                    <div className="px-4 py-3 border-b border-[var(--border)]">
                        <p className="text-xs font-semibold text-[var(--text)]">Sent — awaiting delivery</p>
                    </div>
                    <div className="divide-y divide-[var(--border)]">
                        {sentOrders.map((po) => (
                            <div key={po.id} className="px-4 py-3">
                                <div className="flex items-center justify-between">
                                    <p className="text-sm text-[var(--text)]">
                                        #{po.id} · {po.quantity_ordered}{po.unit} {po.item_name} from {po.supplier_name}
                                    </p>
                                    <button
                                        onClick={() => { setReceivingId(receivingId === po.id ? null : po.id); setReceiveQty(String(po.quantity_ordered)); }}
                                        className="text-[10px] px-2 py-1 rounded bg-[var(--surface-hover)] text-[var(--text-muted)] hover:text-[var(--success)] transition-all">
                                        Record delivery
                                    </button>
                                </div>
                                <AnimatePresence>
                                    {receivingId === po.id && (
                                        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                            className="mt-2 flex gap-2 items-center">
                                            <input placeholder="Quantity actually received" value={receiveQty} onChange={(e) => setReceiveQty(e.target.value)}
                                                type="number" className="flex-1 bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] placeholder-[var(--text-dim)] focus:outline-none" />
                                            <button onClick={() => handleReceive(po.id)} disabled={!receiveQty || submitting}
                                                className="bg-[var(--success)] text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
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

            {/* Reorder settings per item */}
            <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl">
                <div className="px-4 py-3 border-b border-[var(--border)] flex items-center gap-2">
                    <Settings2 className="w-3.5 h-3.5 text-[var(--accent)]" />
                    <p className="text-xs font-semibold text-[var(--text)]">Reorder settings</p>
                </div>
                <div className="divide-y divide-[var(--border)]">
                    {items.length === 0 ? (
                        <p className="text-xs text-[var(--text-dim)] text-center py-6">No stock items yet</p>
                    ) : (
                        items.map((item) => (
                            <div key={item.id} className="px-4 py-3">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-sm text-[var(--text)]">{item.item_name}</p>
                                        <p className="text-[10px] text-[var(--text-dim)] mt-0.5">
                                            {item.par_level != null
                                                ? `Par level ${item.par_level}${item.unit}${item.default_supplier_id ? "" : " · no default supplier"}`
                                                : "Not set up for auto-reorder"}
                                        </p>
                                    </div>
                                    <button onClick={() => openSettings(item)}
                                        className="text-[10px] px-2 py-1 rounded bg-[var(--surface-hover)] text-[var(--text-muted)] hover:text-[var(--accent)] transition-all">
                                        {settingsOpenId === item.id ? "Close" : "Configure"}
                                    </button>
                                </div>
                                <AnimatePresence>
                                    {settingsOpenId === item.id && (
                                        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                            className="mt-2 flex gap-2 items-center flex-wrap">
                                            <input placeholder="Par level (target to restock to)" value={parLevel} onChange={(e) => setParLevel(e.target.value)}
                                                type="number" className="flex-1 min-w-[160px] bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] placeholder-[var(--text-dim)] focus:outline-none" />
                                            <select value={defaultSupplierId} onChange={(e) => setDefaultSupplierId(e.target.value)}
                                                className="flex-1 min-w-[140px] bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] focus:outline-none">
                                                <option value="">No default supplier</option>
                                                {(suppliers || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                                            </select>
                                            <button onClick={() => handleSaveSettings(item.id)} disabled={submitting}
                                                className="bg-[var(--accent)] text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
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

            {/* Suppliers */}
            <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl">
                <div className="px-4 py-3 border-b border-[var(--border)] flex items-center justify-between">
                    <p className="text-xs font-semibold text-[var(--text)]">Suppliers</p>
                    <button onClick={() => setShowSupplierForm(!showSupplierForm)}
                        className="text-[10px] px-2 py-1 rounded bg-[var(--surface-hover)] text-[var(--text-muted)] hover:text-[var(--accent)] transition-all">
                        <Plus className="w-3 h-3 inline mr-0.5" />
                        Add supplier
                    </button>
                </div>
                <AnimatePresence>
                    {showSupplierForm && (
                        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                            className="px-4 py-3 border-b border-[var(--border)] flex gap-2 items-center flex-wrap overflow-hidden">
                            <input placeholder="Supplier name" value={supplierName} onChange={(e) => setSupplierName(e.target.value)}
                                className="flex-1 min-w-[140px] bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] placeholder-[var(--text-dim)] focus:outline-none" />
                            <input placeholder="Phone (for Twilio orders)" value={supplierPhone} onChange={(e) => setSupplierPhone(e.target.value)}
                                className="flex-1 min-w-[160px] bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] placeholder-[var(--text-dim)] focus:outline-none" />
                            <input placeholder="Lead days" value={supplierLeadDays} onChange={(e) => setSupplierLeadDays(e.target.value)}
                                type="number" className="w-24 bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] placeholder-[var(--text-dim)] focus:outline-none" />
                            <button onClick={handleAddSupplier} disabled={!supplierName || submitting}
                                className="bg-[var(--accent)] text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                                {submitting ? "..." : "Add"}
                            </button>
                        </motion.div>
                    )}
                </AnimatePresence>
                <div className="divide-y divide-[var(--border)]">
                    {(suppliers || []).length === 0 ? (
                        <p className="text-xs text-[var(--text-dim)] text-center py-6">No suppliers yet</p>
                    ) : (
                        (suppliers || []).map((s) => (
                            <div key={s.id} className="px-4 py-3">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <p className="text-sm text-[var(--text)]">{s.name}</p>
                                        <p className="text-[10px] text-[var(--text-dim)] mt-0.5">
                                            {s.contact_phone || "No phone on file"} · reliability {s.reliability_score.toFixed(0)}%
                                        </p>
                                    </div>
                                    <button onClick={() => openEditSupplier(s)}
                                        className="text-[10px] px-2 py-1 rounded bg-[var(--surface-hover)] text-[var(--text-muted)] hover:text-[var(--accent)] transition-all flex items-center gap-1">
                                        <Pencil className="w-3 h-3" />
                                        {editingSupplierId === s.id ? "Close" : "Edit"}
                                    </button>
                                </div>
                                <AnimatePresence>
                                    {editingSupplierId === s.id && (
                                        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                            className="mt-2 flex gap-2 items-center flex-wrap overflow-hidden">
                                            <input placeholder="Name" value={editSupplier.name}
                                                onChange={(e) => setEditSupplier({ ...editSupplier, name: e.target.value })}
                                                className="flex-1 min-w-[140px] bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] placeholder-[var(--text-dim)] focus:outline-none" />
                                            <input placeholder="Phone" value={editSupplier.contact_phone}
                                                onChange={(e) => setEditSupplier({ ...editSupplier, contact_phone: e.target.value })}
                                                className="flex-1 min-w-[140px] bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] placeholder-[var(--text-dim)] focus:outline-none" />
                                            <input placeholder="Lead days" value={editSupplier.avg_lead_days} type="number"
                                                onChange={(e) => setEditSupplier({ ...editSupplier, avg_lead_days: e.target.value })}
                                                className="w-24 bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] placeholder-[var(--text-dim)] focus:outline-none" />
                                            <input placeholder="Notes" value={editSupplier.notes}
                                                onChange={(e) => setEditSupplier({ ...editSupplier, notes: e.target.value })}
                                                className="flex-1 min-w-[140px] bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg px-2 py-1.5 text-xs text-[var(--text)] placeholder-[var(--text-dim)] focus:outline-none" />
                                            <button onClick={() => handleSaveSupplier(s.id)} disabled={!editSupplier.name || submitting}
                                                className="bg-[var(--accent)] text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
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

            {/* Order history */}
            {pastOrders.length > 0 && (
                <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl">
                    <div className="px-4 py-3 border-b border-[var(--border)]">
                        <p className="text-xs font-semibold text-[var(--text)]">History</p>
                    </div>
                    <div className="divide-y divide-[var(--border)]">
                        {pastOrders.slice(0, 20).map((po) => (
                            <div key={po.id} className="px-4 py-2.5 flex items-center justify-between">
                                <p className="text-xs text-[var(--text-muted)]">
                                    #{po.id} · {po.item_name} from {po.supplier_name}
                                </p>
                                <span className={`text-[10px] px-1.5 py-0.5 rounded ${po.status === "DELIVERED" ? "bg-[var(--success)]/10 text-[var(--success)]" : po.status === "PARTIAL" ? "bg-[var(--warning)]/10 text-[var(--warning)]" : "bg-[var(--surface-hover)] text-[var(--text-dim)]"}`}>
                                    {po.status.toLowerCase()}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
