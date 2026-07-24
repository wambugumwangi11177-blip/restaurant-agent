"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { demoData, isDemoMode } from "@/lib/demo-data";
import { useToast } from "@/components/ui/Toast";
import { getErrorMessage } from "@/lib/errors";
import type { InventoryItem, StockTransfer, VarianceReport, InventoryAiData } from "./types";

/**
 * All state, data-fetching, and write-action handlers for the Stock
 * workspace (InventoryWorkspace.tsx) — extracted into a hook so the
 * component file can stay focused on composing/rendering the split
 * sub-components (AddItemModal, InventoryList, AdjustStockModal,
 * InventoryInsights, StockAlertsPanel). Behavior is unchanged from the
 * original inline implementation.
 */
export function useInventoryWorkspace() {
    const [items, setItems] = useState<InventoryItem[]>([]);
    const [aiData, setAiData] = useState<InventoryAiData | null>(null);
    const [loading, setLoading] = useState(true);
    const [showAddForm, setShowAddForm] = useState(false);
    const [showReceiveForm, setShowReceiveForm] = useState<number | null>(null);
    const [showAdjustForm, setShowAdjustForm] = useState<number | null>(null);

    // Directive 016/017: store<->kitchen chain of custody (push + pull) +
    // variance report + physical counts. All best-effort — a role without
    // access to /stock/* (e.g. Waiter) simply doesn't see these panels
    // rather than the page erroring.
    const [transfers, setTransfers] = useState<StockTransfer[] | null>(null);
    const [variance, setVariance] = useState<VarianceReport | null>(null);
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
    const newThreshold = "10";

    const [receiveQty, setReceiveQty] = useState("");
    const [receiveCost, setReceiveCost] = useState("");
    const [receiveSupplier, setReceiveSupplier] = useState("");

    const [adjustQty, setAdjustQty] = useState("");
    const [adjustReason, setAdjustReason] = useState("");

    const [submitting, setSubmitting] = useState(false);
    const { showToast, toastNode } = useToast();

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
                ? (transfersRes.data as StockTransfer[]).filter((t) => t.status === "requested" || t.status === "pending")
                : null
        );
        setVariance(varianceRes ? varianceRes.data : null);
        setLoading(false);
    };

    useEffect(() => { fetchData(); }, []);

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
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to add item"), "error");
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
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to record receipt"), "error");
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
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to record adjustment"), "error");
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
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to start transfer"), "error");
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
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to confirm"), "error");
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
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to send request"), "error");
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
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to fulfil request"), "error");
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
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to record count"), "error");
        }
        setSubmitting(false);
    };

    const summary = aiData?.summary || {
        total_items: 0, critical_items: 0, low_stock_items: 0, high_spoilage_items: 0, monthly_spend: 0,
    };
    const predictions = aiData?.predictions || [];
    const alerts = aiData?.alerts || [];

    // Demo stock alerts only in explicit demo mode; a real empty store shows
    // its own (empty) workspace with add controls, not Lavy's fake alerts.
    const isDemo = isDemoMode() && items.length === 0 && alerts.length === 0;
    const demoAlerts = demoData.stockAlerts;

    return {
        // status
        loading, toastNode,
        // derived
        items, summary, predictions, alerts, isDemo, demoAlerts,
        // add item
        showAddForm, setShowAddForm,
        newName, setNewName, newQty, setNewQty, newUnit, setNewUnit,
        handleAddItem,
        // receive / adjust (per item)
        showReceiveForm, setShowReceiveForm,
        showAdjustForm, setShowAdjustForm,
        receiveQty, setReceiveQty, receiveSupplier, setReceiveSupplier,
        adjustQty, setAdjustQty, adjustReason, setAdjustReason,
        handleReceive, handleAdjust,
        // transfers
        transfers,
        showRequestForm, setShowRequestForm, requestItemId, setRequestItemId,
        handleRequestStock,
        showTransferForm, setShowTransferForm, transferItemId, setTransferItemId,
        transferQty, setTransferQty, handleInitiateTransfer,
        fulfillingId, setFulfillingId, fulfillQty, setFulfillQty, handleFulfillTransfer,
        confirmingId, setConfirmingId, confirmQty, setConfirmQty, handleConfirmTransfer,
        // physical count
        showCountForm, setShowCountForm, countItemId, setCountItemId,
        countQty, setCountQty, handleSubmitCount,
        // variance
        variance,
        // shared
        submitting,
    };
}
