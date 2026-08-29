"use client";

import { AlertTriangle, ShieldAlert } from "lucide-react";
import type { VarianceReport, StockAlert } from "./types";

interface StockAlertsPanelProps {
    isDemo: boolean;
    variance: VarianceReport | null;
    alerts: StockAlert[];
}

/**
 * Read-only panels rendered at the bottom of the Stock workspace: the
 * flagged-variance report (directive 016, Controller/Manager/Owner only —
 * null means the role has no /stock/* access, not an error) and the AI
 * "what to do" alerts list. Extracted from InventoryWorkspace.
 */
export default function StockAlertsPanel({ isDemo, variance, alerts }: StockAlertsPanelProps) {
    return (
        <>
            {variance !== null && variance.items?.some((i) => i.flagged) && (
                <div className="bg-surface border border-danger/20 rounded-xl">
                    <div className="px-4 py-3 border-b border-surface-hover flex items-center gap-2">
                        <ShieldAlert className="w-3.5 h-3.5 text-danger" />
                        <p className="text-xs font-semibold text-text">
                            Stock variance — {variance.items.filter((i) => i.flagged).length} item(s) over {(variance.threshold * 100).toFixed(0)}%
                        </p>
                    </div>
                    <div className="divide-y divide-surface-hover">
                        {variance.items.filter((i) => i.flagged).map((i) => (
                            <div key={i.inventory_item_id} className="px-4 py-2.5 flex items-center justify-between">
                                <p className="text-xs text-text">{i.item_name}</p>
                                <p className="text-xs text-danger">
                                    {(i.variance_pct * 100).toFixed(1)}% (expected ~{i.theoretical_usage.toFixed(1)}, actual {i.actual_usage.toFixed(1)})
                                </p>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {!isDemo && alerts.length > 0 && (
                <div className="bg-surface border border-border rounded-xl">
                    <div className="px-4 py-3 border-b border-surface-hover flex items-center gap-2">
                        <AlertTriangle className="w-3.5 h-3.5 text-warning" />
                        <p className="text-xs font-semibold text-text">What to do</p>
                    </div>
                    <div className="divide-y divide-surface-hover">
                        {alerts.map((alert, i: number) => (
                            <div key={i} className="px-4 py-2.5">
                                <p className="text-xs text-text">{alert.message}</p>
                                {alert.action && (
                                    <p className="text-[10px] text-accent mt-0.5">→ {alert.action}</p>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </>
    );
}
