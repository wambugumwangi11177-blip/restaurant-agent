"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ArrowRightLeft, ClipboardList, Plus, Send } from "lucide-react";
import FormField from "@/components/ui/FormField";
import type { InventoryItem, StockTransfer } from "./types";

interface AdjustStockModalProps {
    items: InventoryItem[];
    transfers: StockTransfer[];

    showRequestForm: boolean;
    setShowRequestForm: (v: boolean) => void;
    requestItemId: string;
    setRequestItemId: (v: string) => void;
    onRequestStock: () => void;

    showTransferForm: boolean;
    setShowTransferForm: (v: boolean) => void;
    transferItemId: string;
    setTransferItemId: (v: string) => void;
    transferQty: string;
    setTransferQty: (v: string) => void;
    onInitiateTransfer: () => void;

    fulfillingId: number | null;
    setFulfillingId: (v: number | null) => void;
    fulfillQty: string;
    setFulfillQty: (v: string) => void;
    onFulfillTransfer: (transferId: number) => void;

    confirmingId: number | null;
    setConfirmingId: (v: number | null) => void;
    confirmQty: string;
    setConfirmQty: (v: string) => void;
    onConfirmTransfer: (transferId: number) => void;

    showCountForm: boolean;
    setShowCountForm: (v: boolean) => void;
    countItemId: string;
    setCountItemId: (v: string) => void;
    countQty: string;
    setCountQty: (v: string) => void;
    onSubmitCount: () => void;

    submitting: boolean;
}

/**
 * Store <-> kitchen stock-movement forms — request/send transfers, fulfil +
 * confirm receipt, and physical stock counts (directive 016/017). Extracted
 * from InventoryWorkspace; behavior unchanged.
 */
export default function AdjustStockModal({
    items,
    transfers,
    showRequestForm,
    setShowRequestForm,
    requestItemId,
    setRequestItemId,
    onRequestStock,
    showTransferForm,
    setShowTransferForm,
    transferItemId,
    setTransferItemId,
    transferQty,
    setTransferQty,
    onInitiateTransfer,
    fulfillingId,
    setFulfillingId,
    fulfillQty,
    setFulfillQty,
    onFulfillTransfer,
    confirmingId,
    setConfirmingId,
    confirmQty,
    setConfirmQty,
    onConfirmTransfer,
    showCountForm,
    setShowCountForm,
    countItemId,
    setCountItemId,
    countQty,
    setCountQty,
    onSubmitCount,
    submitting,
}: AdjustStockModalProps) {
    return (
        <>
            {/* Store <-> kitchen transfers, both directions (directive 016
                push, directive 017 pull). */}
            <div className="bg-surface border border-border rounded-xl">
                <div className="px-4 py-3 border-b border-surface-hover flex items-center justify-between flex-wrap gap-2">
                    <div className="flex items-center gap-2">
                        <ArrowRightLeft className="w-3.5 h-3.5 text-accent" />
                        <p className="text-xs font-semibold text-text">Store ↔ kitchen</p>
                    </div>
                    <div className="flex gap-2">
                        <button onClick={() => { setShowRequestForm(!showRequestForm); setShowTransferForm(false); }}
                            className="text-[10px] px-2 py-1 rounded bg-surface-hover text-text-muted hover:text-accent transition-all">
                            <ClipboardList className="w-3 h-3 inline mr-0.5" />
                            Request from store
                        </button>
                        <button onClick={() => { setShowTransferForm(!showTransferForm); setShowRequestForm(false); }}
                            className="text-[10px] px-2 py-1 rounded bg-surface-hover text-text-muted hover:text-accent transition-all">
                            <Send className="w-3 h-3 inline mr-0.5" />
                            Send to kitchen
                        </button>
                    </div>
                </div>

                <AnimatePresence>
                    {showRequestForm && (
                        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                            className="px-4 py-3 border-b border-surface-hover flex gap-2 items-end overflow-hidden">
                            <div className="flex-1 flex flex-col gap-1">
                                <label htmlFor="request-item" className="text-xs text-text-dim">What do you need?</label>
                                <select id="request-item" value={requestItemId} onChange={(e) => setRequestItemId(e.target.value)}
                                    className="w-full bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text focus:outline-none">
                                    <option value="">What do you need?</option>
                                    {items.map((i) => <option key={i.id} value={i.id}>{i.item_name}</option>)}
                                </select>
                            </div>
                            <button onClick={onRequestStock} disabled={!requestItemId || submitting}
                                className="bg-accent text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                                {submitting ? "..." : "Request"}
                            </button>
                        </motion.div>
                    )}
                </AnimatePresence>

                <AnimatePresence>
                    {showTransferForm && (
                        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                            className="px-4 py-3 border-b border-surface-hover flex gap-2 items-end overflow-hidden">
                            <div className="flex-1 flex flex-col gap-1">
                                <label htmlFor="transfer-item" className="text-xs text-text-dim">Item</label>
                                <select id="transfer-item" value={transferItemId} onChange={(e) => setTransferItemId(e.target.value)}
                                    className="w-full bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text focus:outline-none">
                                    <option value="">Select item…</option>
                                    {items.map((i) => <option key={i.id} value={i.id}>{i.item_name}</option>)}
                                </select>
                            </div>
                            <FormField
                                label="Quantity"
                                placeholder="Quantity"
                                value={transferQty}
                                onChange={(e) => setTransferQty(e.target.value)}
                                type="number"
                                className="w-24 bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none"
                            />
                            <button onClick={onInitiateTransfer} disabled={!transferItemId || !transferQty || submitting}
                                className="bg-accent text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                                {submitting ? "..." : "Send"}
                            </button>
                        </motion.div>
                    )}
                </AnimatePresence>

                <div className="divide-y divide-surface-hover">
                    {transfers.length === 0 ? (
                        <p className="text-xs text-text-dim text-center py-6">Nothing pending</p>
                    ) : (
                        transfers.map((t) => {
                            const isRequested = t.status === "requested";
                            const isFulfilling = fulfillingId === t.id;
                            return (
                                <div key={t.id} className="px-4 py-3">
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <p className="text-sm text-text">
                                                #{t.id} · {isRequested ? "requested" : `${t.quantity}${t.unit}`} {t.from_location} → {t.to_location}
                                            </p>
                                            <p className="text-[10px] text-text-dim mt-0.5">
                                                {isRequested ? "Waiting for the store to send it" : "Awaiting confirmation from receiver"}
                                            </p>
                                        </div>
                                        {isRequested ? (
                                            <button
                                                onClick={() => { setFulfillingId(isFulfilling ? null : t.id); setFulfillQty(""); }}
                                                className="text-[10px] px-2 py-1 rounded bg-surface-hover text-text-muted hover:text-accent transition-all">
                                                Fulfil
                                            </button>
                                        ) : (
                                            <button
                                                onClick={() => { setConfirmingId(confirmingId === t.id ? null : t.id); setConfirmQty(String(t.quantity)); }}
                                                className="text-[10px] px-2 py-1 rounded bg-surface-hover text-text-muted hover:text-success transition-all">
                                                Confirm receipt
                                            </button>
                                        )}
                                    </div>
                                    <AnimatePresence>
                                        {isFulfilling && (
                                            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                                className="mt-2 flex gap-2 items-end">
                                                <FormField
                                                    label="Quantity being sent"
                                                    placeholder="Quantity being sent"
                                                    value={fulfillQty}
                                                    onChange={(e) => setFulfillQty(e.target.value)}
                                                    type="number"
                                                    className="flex-1 bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none"
                                                />
                                                <button onClick={() => onFulfillTransfer(t.id)} disabled={!fulfillQty || submitting}
                                                    className="bg-accent text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                                                    {submitting ? "..." : "Send"}
                                                </button>
                                            </motion.div>
                                        )}
                                    </AnimatePresence>
                                    <AnimatePresence>
                                        {confirmingId === t.id && (
                                            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                                className="mt-2 flex gap-2 items-end">
                                                <FormField
                                                    label="Actual quantity received"
                                                    placeholder="Actual quantity received"
                                                    value={confirmQty}
                                                    onChange={(e) => setConfirmQty(e.target.value)}
                                                    type="number"
                                                    className="flex-1 bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none"
                                                />
                                                <button onClick={() => onConfirmTransfer(t.id)} disabled={!confirmQty || submitting}
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

            {/* Physical stock count (directive 017) — the independent check
                that keeps theft/shrinkage detection meaningful once
                ingredient deduction is automatic. */}
            <div className="bg-surface border border-border rounded-xl">
                <div className="px-4 py-3 border-b border-surface-hover flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <ClipboardList className="w-3.5 h-3.5 text-accent" />
                        <p className="text-xs font-semibold text-text">Physical count</p>
                    </div>
                    <button onClick={() => setShowCountForm(!showCountForm)}
                        className="text-[10px] px-2 py-1 rounded bg-surface-hover text-text-muted hover:text-accent transition-all">
                        <Plus className="w-3 h-3 inline mr-0.5" />
                        Count an item
                    </button>
                </div>
                <AnimatePresence>
                    {showCountForm && (
                        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                            className="px-4 py-3 flex gap-2 items-end overflow-hidden">
                            <div className="flex-1 flex flex-col gap-1">
                                <label htmlFor="count-item" className="text-xs text-text-dim">What did you count?</label>
                                <select id="count-item" value={countItemId} onChange={(e) => setCountItemId(e.target.value)}
                                    className="w-full bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text focus:outline-none">
                                    <option value="">What did you count?</option>
                                    {items.map((i) => <option key={i.id} value={i.id}>{i.item_name}</option>)}
                                </select>
                            </div>
                            <FormField
                                label="What's actually there"
                                placeholder="What's actually there"
                                value={countQty}
                                onChange={(e) => setCountQty(e.target.value)}
                                type="number"
                                className="w-32 bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text placeholder-text-dim focus:outline-none"
                            />
                            <button onClick={onSubmitCount} disabled={!countItemId || !countQty || submitting}
                                className="bg-accent text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                                {submitting ? "..." : "Record"}
                            </button>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        </>
    );
}
