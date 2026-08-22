"use client";

import { Boxes } from "lucide-react";
import { formatKES } from "@/lib/format";
import { useAiModule } from "@/lib/useAiModule";
import { MiniStat } from "@/components/ai/MiniStat";
import { ModuleShell } from "@/components/ai/ModuleShell";

interface InventoryPredictionsData {
    summary: {
        total_items: number;
        total_inventory_value: number;
        critical_items: number;
        low_stock_items: number;
        high_spoilage_items: number;
    };
    predictions: {
        id: number;
        name: string;
        unit: string;
        current_stock: number;
        low_stock_threshold: number | null;
        status: string;
        daily_usage_avg: number;
        consumption_trend: string;
    }[];
}

const statusTone: Record<string, string> = {
    critical: "text-red-400",
    low: "text-amber-400",
};

export default function InventoryPredictionsSection() {
    const { data, loading, error, retry } = useAiModule<InventoryPredictionsData>("/ai/inventory-predictions");

    return (
        <ModuleShell
            icon={Boxes}
            title="Inventory Forecast"
            subtitle="Depletion prediction per item — what runs out soon, and how fast it's moving."
            loading={loading}
            error={error}
            onRetry={retry}
        >
            {data && (
                <>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                        <MiniStat label="Items Tracked" value={String(data.summary.total_items)} />
                        <MiniStat label="Stock Value" value={formatKES(data.summary.total_inventory_value)} />
                        <MiniStat
                            label="Low / Critical"
                            value={`${data.summary.low_stock_items} / ${data.summary.critical_items}`}
                            tone={data.summary.critical_items > 0 ? "warn" : data.summary.low_stock_items > 0 ? "warn" : "ok"}
                        />
                        <MiniStat
                            label="Spoilage Risk"
                            value={String(data.summary.high_spoilage_items)}
                            tone={data.summary.high_spoilage_items > 0 ? "warn" : "ok"}
                        />
                    </div>
                    {data.predictions.length === 0 ? (
                        <p className="text-text-dim text-sm">No inventory items tracked yet — add stock items to see depletion forecasts.</p>
                    ) : (
                        <div className="space-y-1.5">
                            {data.predictions
                                .filter(p => p.status === "critical" || p.status === "low")
                                .slice(0, 5)
                                .map(p => (
                                    <div key={p.id} className="flex items-center justify-between gap-3 p-2.5 rounded-lg bg-surface border border-surface-hover text-sm">
                                        <span className="text-text">{p.name}</span>
                                        <span className={`font-medium ${statusTone[p.status] || "text-text"}`}>
                                            {p.current_stock} {p.unit} left
                                        </span>
                                        <span className="text-text-dim text-xs text-right hidden sm:block">
                                            using ~{p.daily_usage_avg.toFixed(1)} {p.unit}/day
                                            {p.consumption_trend === "accelerating" && " · speeding up"}
                                        </span>
                                    </div>
                                ))}
                            {data.predictions.filter(p => p.status === "critical" || p.status === "low").length === 0 && (
                                <p className="text-emerald-400 text-sm">All items comfortably stocked.</p>
                            )}
                        </div>
                    )}
                </>
            )}
        </ModuleShell>
    );
}
