"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { ShieldAlert, ShieldCheck } from "lucide-react";
import type { VarianceReport } from "./types";

/**
 * Read-only variance/shrinkage report — for Controller, who has `inventory` =
 * R (directive 015: financial/loss-prevention role, deliberately no
 * receive/adjust/transfer write access — separation of duties from
 * Stockkeeper). Extracted out of InventoryWorkspace's variance section
 * rather than giving Controller the whole write-heavy workspace.
 */
export default function VarianceReportPanel() {
    const [variance, setVariance] = useState<VarianceReport | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get("/stock/variance-report").then((res) => setVariance(res.data)).catch(() => setVariance(null)).finally(() => setLoading(false));
    }, []);

    if (loading) {
        return (
            <div className="space-y-3">
                {[...Array(3)].map((_, i) => (
                    <div key={i} className="bg-surface rounded-xl h-14 animate-pulse" />
                ))}
            </div>
        );
    }

    const flagged = (variance?.items || []).filter((i) => i.flagged);

    return (
        <div className="space-y-5">
            <div>
                <h1 className="text-xl font-bold text-text">Stock Variance</h1>
                <p className="text-sm text-text-dim mt-0.5">
                    Theoretical usage (from recipes) vs. actual stock movement — a real gap flags possible shrinkage.
                </p>
            </div>

            {flagged.length === 0 ? (
                <div className="bg-surface border border-border rounded-xl px-4 py-8 text-center">
                    <ShieldCheck className="w-8 h-8 text-success mx-auto mb-3" />
                    <p className="text-sm text-text-dim">No items over the {((variance?.threshold ?? 0.03) * 100).toFixed(0)}% variance threshold</p>
                </div>
            ) : (
                <div className="bg-surface border border-danger/20 rounded-xl">
                    <div className="px-4 py-3 border-b border-surface-hover flex items-center gap-2">
                        <ShieldAlert className="w-3.5 h-3.5 text-danger" />
                        <p className="text-xs font-semibold text-text">
                            {flagged.length} item(s) over {((variance?.threshold ?? 0.03) * 100).toFixed(0)}%
                        </p>
                    </div>
                    <div className="divide-y divide-surface-hover">
                        {flagged.map((i) => (
                            <div key={i.inventory_item_id} className="px-4 py-3 flex items-center justify-between">
                                <p className="text-sm text-text">{i.item_name}</p>
                                <p className="text-xs text-danger">
                                    {(i.variance_pct * 100).toFixed(1)}% (expected ~{i.theoretical_usage.toFixed(1)}, actual {i.actual_usage.toFixed(1)})
                                </p>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
