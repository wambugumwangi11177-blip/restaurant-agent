"use client";

import type { InventorySummary } from "./types";

interface InventoryInsightsProps {
    summary: InventorySummary;
    predictionsCount: number;
}

/**
 * Read-only "overview" panel for the Stock workspace, rendered above the
 * item list: the AI stock overview. Extracted from InventoryWorkspace to keep
 * the orchestrator focused on state/data-fetching — it renders no form.
 */
export default function InventoryInsights({
    summary,
    predictionsCount,
}: InventoryInsightsProps) {
    return (
        <>
            {/* AI overview */}
            {(summary.total_items > 0 || predictionsCount > 0) && (
                <div className="bg-surface border border-border rounded-xl">
                    <div className="px-4 py-3 border-b border-surface-hover">
                        <p className="text-xs font-semibold text-text">Stock overview</p>
                    </div>
                    <div className="px-4 py-3 space-y-2">
                        {summary.critical_items > 0 && (
                            <p className="text-xs text-danger">
                                ⚠️ {summary.critical_items} item{summary.critical_items > 1 ? "s have" : " has"} run out — restock now
                            </p>
                        )}
                        {summary.low_stock_items > 0 && (
                            <p className="text-xs text-warning">
                                📦 {summary.low_stock_items} item{summary.low_stock_items > 1 ? "s are" : " is"} running low
                            </p>
                        )}
                        {summary.high_spoilage_items > 0 && (
                            <p className="text-xs text-text-muted">
                                🗑️ {summary.high_spoilage_items} item{summary.high_spoilage_items > 1 ? "s" : ""} might spoil soon
                            </p>
                        )}
                        {summary.monthly_spend > 0 && (
                            <p className="text-xs text-text-muted">
                                💰 Spending about KES {(summary.monthly_spend / 100).toLocaleString("en-KE")}/month on stock
                            </p>
                        )}
                    </div>
                </div>
            )}
        </>
    );
}
