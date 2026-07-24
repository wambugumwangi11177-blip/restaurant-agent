"use client";

import { Plus } from "lucide-react";
import { useInventoryWorkspace } from "./useInventoryWorkspace";
import AddItemModal from "./AddItemModal";
import InventoryList from "./InventoryList";
import AdjustStockModal from "./AdjustStockModal";
import InventoryInsights from "./InventoryInsights";
import StockAlertsPanel from "./StockAlertsPanel";

/**
 * Full stock workspace — extracted from the original dashboard/inventory/
 * page.tsx unmodified. Already self-gates correctly for every tier with
 * `inventory` access: write actions (add/receive/adjust, transfers, counts)
 * simply fail server-side with a 403 for read-only tiers, and the
 * variance-report panel already only renders when the backend actually
 * returns data (Controller/Manager/Owner) — a role without /stock/* access
 * (e.g. Kitchen's read-only view) gets a null response, not an error, so the
 * panel is silently absent rather than broken. Reused as-is by Owner and by
 * Stockkeeper (both have full inventory RW + transfer/count access per
 * directive 015) — Controller gets a separate, read-only VarianceReportPanel
 * instead of this whole workspace, since Controller has no write access here
 * at all.
 *
 * All state/data-fetching/handlers live in useInventoryWorkspace(); this
 * file is pure composition of the split sub-components (AddItemModal,
 * InventoryList, AdjustStockModal, InventoryInsights, StockAlertsPanel).
 */
export default function InventoryWorkspace() {
    const w = useInventoryWorkspace();

    if (w.loading) {
        return (
            <div className="space-y-3">
                {[...Array(4)].map((_, i) => (
                    <div key={i} className="bg-surface rounded-xl h-14 animate-pulse" />
                ))}
            </div>
        );
    }

    return (
        <div className="space-y-5">
            {w.toastNode}

            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-xl font-bold text-text">Stock</h1>
                    <p className="text-sm text-text-dim mt-0.5">
                        {w.isDemo ? "Demo stock alerts" : `${w.items.length} item${w.items.length !== 1 ? "s" : ""} tracked from your store`}
                    </p>
                </div>
                <div className="flex gap-2">
                    <button onClick={() => w.setShowAddForm(!w.showAddForm)}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-accent/10 border border-accent/30 rounded-lg text-xs text-accent hover:bg-accent/20 transition-all">
                        <Plus className="w-3 h-3" />
                        Add Item
                    </button>
                </div>
            </div>

            {/* Demo Banner */}
            {w.isDemo && (
                <div className="flex items-center gap-2 px-3 py-1.5 bg-accent/8 border border-accent/20 rounded-lg">
                    <span className="text-[10px] text-accent">📊 Demo Mode — Showing sample data for Lavy restaurant</span>
                </div>
            )}

            <AddItemModal
                show={w.showAddForm}
                onClose={() => w.setShowAddForm(false)}
                newName={w.newName}
                setNewName={w.setNewName}
                newQty={w.newQty}
                setNewQty={w.setNewQty}
                newUnit={w.newUnit}
                setNewUnit={w.setNewUnit}
                submitting={w.submitting}
                onSubmit={w.handleAddItem}
            />

            <InventoryInsights
                isDemo={w.isDemo}
                demoAlerts={w.demoAlerts}
                summary={w.summary}
                predictionsCount={w.predictions.length}
            />

            {/* Real: Stock items */}
            {!w.isDemo && (
                <InventoryList
                    items={w.items}
                    predictions={w.predictions}
                    showReceiveForm={w.showReceiveForm}
                    setShowReceiveForm={w.setShowReceiveForm}
                    showAdjustForm={w.showAdjustForm}
                    setShowAdjustForm={w.setShowAdjustForm}
                    receiveQty={w.receiveQty}
                    setReceiveQty={w.setReceiveQty}
                    receiveSupplier={w.receiveSupplier}
                    setReceiveSupplier={w.setReceiveSupplier}
                    adjustQty={w.adjustQty}
                    setAdjustQty={w.setAdjustQty}
                    adjustReason={w.adjustReason}
                    setAdjustReason={w.setAdjustReason}
                    submitting={w.submitting}
                    onReceive={w.handleReceive}
                    onAdjust={w.handleAdjust}
                />
            )}

            {/* Store <-> kitchen transfers + physical counts. Only shown to
                roles that can reach /stock/transfers — Waiter/Supervisor get
                null back and the panels don't render, rather than an error
                state. */}
            {w.transfers !== null && (
                <AdjustStockModal
                    items={w.items}
                    transfers={w.transfers}
                    showRequestForm={w.showRequestForm}
                    setShowRequestForm={w.setShowRequestForm}
                    requestItemId={w.requestItemId}
                    setRequestItemId={w.setRequestItemId}
                    onRequestStock={w.handleRequestStock}
                    showTransferForm={w.showTransferForm}
                    setShowTransferForm={w.setShowTransferForm}
                    transferItemId={w.transferItemId}
                    setTransferItemId={w.setTransferItemId}
                    transferQty={w.transferQty}
                    setTransferQty={w.setTransferQty}
                    onInitiateTransfer={w.handleInitiateTransfer}
                    fulfillingId={w.fulfillingId}
                    setFulfillingId={w.setFulfillingId}
                    fulfillQty={w.fulfillQty}
                    setFulfillQty={w.setFulfillQty}
                    onFulfillTransfer={w.handleFulfillTransfer}
                    confirmingId={w.confirmingId}
                    setConfirmingId={w.setConfirmingId}
                    confirmQty={w.confirmQty}
                    setConfirmQty={w.setConfirmQty}
                    onConfirmTransfer={w.handleConfirmTransfer}
                    showCountForm={w.showCountForm}
                    setShowCountForm={w.setShowCountForm}
                    countItemId={w.countItemId}
                    setCountItemId={w.setCountItemId}
                    countQty={w.countQty}
                    setCountQty={w.setCountQty}
                    onSubmitCount={w.handleSubmitCount}
                    submitting={w.submitting}
                />
            )}

            <StockAlertsPanel isDemo={w.isDemo} variance={w.variance} alerts={w.alerts} />
        </div>
    );
}
