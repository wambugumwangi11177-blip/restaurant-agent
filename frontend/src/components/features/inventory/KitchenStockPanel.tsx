"use client";
import {useListQuery} from "@/lib/owner/useListQuery";
import {useDailyReview} from "@/lib/owner/useDailyReview";

import { useEffect, useState } from "react";
import {useAuth} from "@/context/AuthContext";
import api from "@/lib/api";
import { AnimatePresence, motion } from "framer-motion";
import { Package, ClipboardList } from "lucide-react";
import { useToast } from "@/components/ui/Toast";
import FormField from "@/components/ui/FormField";
import { getErrorMessage } from "@/lib/errors";
import type { InventoryItem, StockTransfer } from "./types";

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
export default function KitchenStockPanel({ focused = false }: { focused?: boolean }) {
 const [tool]=useListQuery("tool","receipts");
 const reviewDay=useDailyReview();
    const {user}=useAuth();
    const [failure,setFailure]=useState("");
    const [photo,setPhoto]=useState<File|null>(null);
    const [items, setItems] = useState<InventoryItem[]>([]);
    const [transfers, setTransfers] = useState<StockTransfer[]>([]);
    const [loading, setLoading] = useState(true);

    const [showRequestForm, setShowRequestForm] = useState(false);
    const [requestItemId, setRequestItemId] = useState("");
    const [confirmingId, setConfirmingId] = useState<number | null>(null);
    const [confirmQty, setConfirmQty] = useState("");

    const [submitting, setSubmitting] = useState(false);
    const { showToast, toastNode } = useToast();

    const fetchData = async () => {
        const [invRes, transfersRes] = await Promise.all([
            api.get("/inventory/").catch(() => {setFailure("Could not read inventory. Reload to retry.");return {data:[]};}),
            api.get("/stock/transfers").catch(() => {setFailure("Could not read handovers. Reload to retry.");return {data:[]};}),
        ]);
        setItems(Array.isArray(invRes.data) ? invRes.data : []);
        setTransfers(
            Array.isArray(transfersRes.data)
                ? (transfersRes.data as StockTransfer[]).filter((t) => t.status === "requested" || t.status === "pending")
                : []
        );
        setLoading(false);
    };

    useEffect(() => { fetchData(); }, [reviewDay]);

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
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to send request"), "error");
        }
        setSubmitting(false);
    };

    const handleConfirmTransfer = async (transferId: number) => {
        if (!confirmQty) return;
        setSubmitting(true);
        try {
            let photo_ref=null;
            if(photo){const form=new FormData();form.append('file',photo);photo_ref=(await api.post('/api/v1/owner/operations/receipts',form,{headers:{'Content-Type':'multipart/form-data'}})).data.receipt_ref;}
            const res = await api.post(`/stock/transfers/${transferId}/confirm`, {
                photo_ref,
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
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to confirm"), "error");
        }
        setSubmitting(false);
    };

    if (loading) {
        return (
            <div className="space-y-3">
                {[...Array(3)].map((_, i) => (
                    <div key={i} className="bg-surface rounded-xl h-14 animate-pulse" />
                ))}
            </div>
        );
    }

    return (
        <div className="space-y-5">
            {toastNode}{failure&&<p role="alert" className="rounded-xl bg-red-50 p-3 text-red-900">{failure}</p>}

            <div>
                <h1 className="text-xl font-bold text-text">{focused?(tool==="request"?"Request stock from store":"Kitchen receipt confirmations"):"Stock"}</h1>
                <p className="text-sm text-text-dim mt-0.5">
                    {focused?(tool==="request"?"Choose an ingredient to request from the store.":"Confirm the quantity that actually arrived from the store."):"Request ingredients from the store and confirm your own count when they arrive."}
                </p>
            </div>

            {/* Request from store */}
            {(!focused||tool==="request")&&<div className="bg-surface border border-border rounded-xl">
                <div className="px-4 py-3 border-b border-surface-hover flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <ClipboardList className="w-3.5 h-3.5 text-accent" />
                        <p className="text-xs font-semibold text-text">Request from store</p>
                    </div>
                    <button onClick={() => setShowRequestForm(!showRequestForm)}
                        className="text-[10px] px-2 py-1 rounded bg-surface-hover text-text-muted hover:text-accent transition-all">
                        {showRequestForm ? "Cancel" : "What do you need?"}
                    </button>
                </div>
                <AnimatePresence>
                    {showRequestForm && (
                        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                            className="px-4 py-3 flex gap-2 items-end overflow-hidden">
                            <div className="flex-1 flex flex-col gap-1">
                                <label htmlFor="kitchen-request-item" className="text-xs text-text-dim">Select an ingredient</label>
                                <select id="kitchen-request-item" value={requestItemId} onChange={(e) => setRequestItemId(e.target.value)}
                                    className="w-full bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text focus:outline-none">
                                    <option value="">Select an ingredient…</option>
                                    {items.map((i) => <option key={i.id} value={i.id}>{i.item_name}</option>)}
                                </select>
                            </div>
                            <button onClick={handleRequestStock} disabled={!requestItemId || submitting}
                                className="bg-accent text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                                {submitting ? "..." : "Request"}
                            </button>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>

            }
            {/* Pending requests / awaiting confirmation */}
            <div className="bg-surface border border-border rounded-xl">
                <div className="px-4 py-3 border-b border-surface-hover">
                    <p className="text-xs font-semibold text-text">Requests & deliveries</p>
                </div>
                <div className="divide-y divide-surface-hover">
                    {transfers.filter(t=>!focused||(tool==="request"?t.status==="requested":t.status==="pending")).length === 0 ? (
                        <p className="text-xs text-text-dim text-center py-6">Nothing pending</p>
                    ) : (
                        transfers.filter(t=>!focused||(tool==="request"?t.status==="requested":t.status==="pending")).map((t) => {
                            const isRequested = t.status === "requested";
                            return (
                                <div key={t.id} className="px-4 py-3">
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <p className="text-sm text-text">
                                                #{t.id} · {isRequested ? "requested" : `${t.quantity}${t.unit}`} {t.from_location} → {t.to_location}
                                            </p>
                                            <p className="text-[10px] text-text-dim mt-0.5">
                                                {isRequested ? "Waiting for the store to send it" : "Ready to collect — confirm what actually arrived"}
                                            </p>
                                        </div>
                                        {!isRequested && t.initiated_by_user_id!==user?.id && (
                                            <button
                                                onClick={() => { setConfirmingId(confirmingId === t.id ? null : t.id); setConfirmQty("");setPhoto(null); }}
                                                className="text-[10px] px-2 py-1 rounded bg-surface-hover text-text-muted hover:text-success transition-all">
                                                Confirm receipt
                                            </button>
                                        )}
                                    </div>
                                    <AnimatePresence>
                                        {confirmingId === t.id && (
                                            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                                className="mt-2 flex gap-2 items-end">
                                                <FormField
                                                    label="Actual quantity received"
                                                    aria-label="Actual quantity received" placeholder="Actual quantity received" min="0" step="any"
                                                    value={confirmQty}
                                                    onChange={(e) => setConfirmQty(e.target.value)}
                                                    type="number"
                                                    className="flex-1 bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none"
                                                />
                                                <label className="text-xs">Photo (optional)<input type="file" accept="image/*" capture="environment" onChange={e=>setPhoto(e.target.files?.[0]??null)}/></label>
                                                <button onClick={() => handleConfirmTransfer(t.id)} disabled={!confirmQty || submitting}
                                                    className="bg-success text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
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
            {!focused&&<div className="bg-surface border border-border rounded-xl">
                <div className="px-4 py-3 border-b border-surface-hover flex items-center gap-2">
                    <Package className="w-3.5 h-3.5 text-accent" />
                    <p className="text-xs font-semibold text-text">Stock preview · first 5 items</p>
                </div>
                <div className="divide-y divide-surface-hover">
                    {items.length === 0 ? (
                        <p className="text-xs text-text-dim text-center py-8">No stock items tracked yet</p>
                    ) : (
                        items.slice(0,5).map((item) => {
                            const isLow = item.quantity <= item.low_stock_threshold;
                            const isOut = item.quantity <= 0;
                            return (
                                <div key={item.id} className="px-4 py-3 flex items-center gap-3">
                                    <div className={`w-2 h-2 rounded-full flex-shrink-0 ${isOut ? "bg-danger" : isLow ? "bg-warning" : "bg-success"}`} />
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm text-text">{item.item_name}</p>
                                        <span className={`text-xs ${isLow ? "text-warning" : "text-text-muted"}`}>
                                            {item.quantity} {item.unit}
                                        </span>
                                    </div>
                                    {isOut && <span className="text-[10px] text-danger font-semibold">Out</span>}
                                    {!isOut && isLow && <span className="text-[10px] text-warning font-semibold">Low</span>}
                                </div>
                            );
                        })
                    )}
                </div>
            </div>}

        </div>
    );
}
