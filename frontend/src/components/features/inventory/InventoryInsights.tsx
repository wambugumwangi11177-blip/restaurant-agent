"use client";

import { motion } from "framer-motion";
import { AlertTriangle } from "lucide-react";
import type { InventorySummary } from "./types";

interface InventoryInsightsProps {
    isDemo: boolean;
    demoAlerts: { item: string; urgency: string; quantity: string; hours_left: number }[];
    summary: InventorySummary;
    predictionsCount: number;
}

/**
 * Read-only "overview" panels for the Stock workspace, rendered above the
 * item list: demo alerts (demo mode only) and the AI stock overview.
 * Extracted from InventoryWorkspace to keep the orchestrator focused on
 * state/data-fetching — neither panel renders a form.
 */
export default function InventoryInsights({
    isDemo,
    demoAlerts,
    summary,
    predictionsCount,
}: InventoryInsightsProps) {
    return (
        <>
            {/* Demo: Stock Alerts with urgency colours */}
            {isDemo && (
                <div className="bg-surface border border-border rounded-xl">
                    <div className="px-4 py-3 border-b border-surface-hover flex items-center gap-2">
                        <AlertTriangle className="w-3.5 h-3.5 text-warning" />
                        <p className="text-xs font-semibold text-text">Stock Alerts</p>
                    </div>
                    <div className="divide-y divide-surface-hover">
                        {demoAlerts.map((alert, i) => {
                            const isUrgent = alert.urgency === "URGENT";
                            return (
                                <motion.div
                                    key={i}
                                    initial={{ opacity: 0, x: -8 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: i * 0.08 }}
                                    className="px-4 py-3 flex items-center gap-3"
                                >
                                    <div className={`w-2 h-2 rounded-full flex-shrink-0 ${isUrgent ? "bg-danger animate-pulse" : "bg-warning"}`} />
                                    <div className="flex-1">
                                        <div className="flex items-center gap-2">
                                            <p className="text-sm text-text">{alert.item}</p>
                                            <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded ${isUrgent
                                                ? "bg-danger/10 text-danger"
                                                : "bg-warning/10 text-warning"
                                                }`}>
                                                {alert.urgency}
                                            </span>
                                        </div>
                                        <p className="text-[10px] text-text-dim mt-0.5">
                                            {alert.quantity} remaining · ~{alert.hours_left}h left
                                        </p>
                                    </div>
                                    <span className={`text-xs font-semibold ${isUrgent ? "text-danger" : "text-warning"}`}>
                                        {isUrgent ? "Reorder now" : "Reorder soon"}
                                    </span>
                                </motion.div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* Real: AI overview */}
            {!isDemo && (summary.total_items > 0 || predictionsCount > 0) && (
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
