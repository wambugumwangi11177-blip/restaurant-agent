"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
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
            api.get("/api/v1/inventory/").catch(() => ({ data: [] })),
            api.get("/api/v1/ai/inventory-predictions").catch(() => ({ data: null })),
            api.get("/api/v1/stock/transfers").catch(() => null),
            api.get("/api/v1/stock/variance-report?hours=168").catch(() => null),
        ]);
        setItems(Array.isArray(invRes.data) ? invRes.data : []);
        setAiData(aiRes.data);
        setTransfers(
            transfersRes
                ? (transfersRes.data as StockTransfer[]).filter((t) => t.status === "requested" || t.status === "pending" || t.status === "disputed")
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
            await api.post("/api/v1/inventory/", {
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
            const res = await api.post(`/api/v1/inventory/${itemId}/receive`, {
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
            const res = await api.post(`/api/v1/inventory/${itemId}/adjust`, {
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
            await api.post("/api/v1/stock/transfers", {
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

    const handleRequestStock = async () => {
        if (!requestItemId) return;
        setSubmitting(true);
        try {
            await api.post("/api/v1/stock/transfers/request", {
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
            await api.post(`/api/v1/stock/transfers/${transferId}/fulfil`, {
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
            const res = await api.post("/api/v1/stock/counts", {
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

    const handleRenameItem = async (itemId: number, itemName: string) => {
        const next = window.prompt("Item name", itemName);
        if (!next || next === itemName) return;
        setSubmitting(true);
        try {
            await api.put(`/api/v1/inventory/${itemId}`, { item_name: next });
            showToast("Item renamed");
            await fetchData();
        } catch (err) {
            showToast(getErrorMessage(err, "Could not rename this item"), "error");
        }
        setSubmitting(false);
    };

    const handleDeleteItem = async (itemId: number, itemName: string) => {
        if (!window.confirm(`Remove ${itemName}? Items with a stock history stay.`)) return;
        setSubmitting(true);
        try {
            await api.delete(`/api/v1/inventory/${itemId}`);
            showToast("Item removed");
            await fetchData();
        } catch (err) {
            showToast(getErrorMessage(err, "Could not remove this item"), "error");
        }
        setSubmitting(false);
    };

    const summary = aiData?.summary || {
        total_items: 0, critical_items: 0, low_stock_items: 0, high_spoilage_items: 0, monthly_spend: 0,
    };
    const predictions = aiData?.predictions || [];
    const alerts = aiData?.alerts || [];

    return {
        // status
        loading, toastNode,
        // derived
        items, summary, predictions, alerts,
        // add item
        showAddForm, setShowAddForm,
        newName, setNewName, newQty, setNewQty, newUnit, setNewUnit,
        handleAddItem,
        // receive / adjust (per item)
        showReceiveForm, setShowReceiveForm,
        showAdjustForm, setShowAdjustForm,
        receiveQty, setReceiveQty, receiveSupplier, setReceiveSupplier,
        adjustQty, setAdjustQty, adjustReason, setAdjustReason,
        handleReceive, handleAdjust, handleRenameItem, handleDeleteItem,
        // transfers
        transfers,
        showRequestForm, setShowRequestForm, requestItemId, setRequestItemId,
        handleRequestStock,
        showTransferForm, setShowTransferForm, transferItemId, setTransferItemId,
        transferQty, setTransferQty, handleInitiateTransfer,
        fulfillingId, setFulfillingId, fulfillQty, setFulfillQty, handleFulfillTransfer,
        // physical count
        showCountForm, setShowCountForm, countItemId, setCountItemId,
        countQty, setCountQty, handleSubmitCount,
        // variance
        variance,
        // shared
        submitting,
    };
}
