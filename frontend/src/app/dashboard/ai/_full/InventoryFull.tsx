"use client";

import { useAiModule } from "@/lib/useAiModule";
import { StatGrid, DataTable, SectionTitle, money, LoadingBlock } from "./shared";

interface Pred { id: number; name: string; unit: string; current_stock: number; current_value?: number; low_stock_threshold?: number; status: string; daily_usage_avg?: number; daily_usage_recent_7d?: number; consumption_trend?: string; consumption_trend_pct?: number; velocity?: string; total_consumed_30d?: number; total_restocked_30d?: number; peak_usage_day?: string }
interface InventoryData {
    summary: { total_items?: number; total_inventory_value?: number; critical_items?: number; low_stock_items?: number; high_spoilage_items?: number; abc_breakdown?: Record<string, number> };
    predictions: Pred[];
    alerts: { item: string; message: string; severity: string; action?: string }[];
}

const statusTone = (s: string) => s === "critical" ? "text-red-400" : s === "low" ? "text-amber-400" : "text-emerald-400";

export default function InventoryFull() {
    const { data, loading, error, retry } = useAiModule<InventoryData>("/ai/inventory-predictions");
    if (loading) return <LoadingBlock />;
    if (error) return <div className="flex items-center gap-3"><p className="text-text-dim text-sm">{error}</p><button onClick={retry} className="px-3 py-1.5 rounded-lg bg-[var(--accent)] text-bg text-sm font-semibold">Retry</button></div>;
    if (!data) return null;
    const s = data.summary ?? {};
    const abc = s.abc_breakdown ?? {};
    const sorted = [...(data.predictions ?? [])].sort((a, b) => {
        const rank = (x: string) => (x === "critical" ? 0 : x === "low" ? 1 : 2);
        return rank(a.status) - rank(b.status);
    });
    return (
        <div>
            <StatGrid stats={[
                { label: "Items Tracked", value: String(s.total_items ?? data.predictions.length) },
                { label: "Stock Value", value: money(s.total_inventory_value) },
                { label: "Low / Critical", value: `${s.low_stock_items ?? 0} / ${s.critical_items ?? 0}`, tone: ((s.critical_items ?? 0) > 0 || (s.low_stock_items ?? 0) > 0) ? "warn" : "ok" },
                { label: "ABC (A/B/C)", value: `${abc.A ?? 0} / ${abc.B ?? 0} / ${abc.C ?? 0}` },
            ]} />
            <SectionTitle>Every item — depletion forecast (low/critical first)</SectionTitle>
            <DataTable
                columns={[
                    { key: "name", label: "Item" },
                    { key: "status", label: "Status", render: r => <span className={`font-medium ${statusTone(String(r.status))}`}>{String(r.status)}</span> },
                    { key: "current_stock", label: "Stock", render: r => `${r.current_stock} ${r.unit}` },
                    { key: "low_stock_threshold", label: "Threshold" },
                    { key: "daily_usage_avg", label: "Usage/day", render: r => `${Number(r.daily_usage_avg ?? 0).toFixed(2)} ${r.unit}` },
                    { key: "consumption_trend", label: "Trend", render: r => `${r.consumption_trend ?? "—"}${r.consumption_trend_pct != null ? ` (${r.consumption_trend_pct}%)` : ""}` },
                    { key: "velocity", label: "Velocity" },
                    { key: "peak_usage_day", label: "Peak day" },
                    { key: "total_consumed_30d", label: "Used 30d" },
                    { key: "total_restocked_30d", label: "Restocked 30d" },
                ]}
                rows={sorted } />
            <SectionTitle>All alerts ({data.alerts.length})</SectionTitle>
            <div className="space-y-1.5">
                {data.alerts.map((a, i) => (
                    <div key={i} className={`p-3 rounded-lg border text-sm ${a.severity === "critical" ? "bg-red-500/5 border-red-500/20" : a.severity === "warning" ? "bg-amber-500/5 border-amber-500/20" : "bg-surface border-surface-hover"}`}>
                        <p className="text-text"><span className="font-medium">{a.item}:</span> {a.message}</p>
                        {a.action && <p className="text-xs text-[var(--accent)] mt-1">→ {a.action.replace(/_/g, " ")}</p>}
                    </div>
                ))}
                {data.alerts.length === 0 && <p className="text-text-dim text-sm">No active alerts.</p>}
            </div>
        </div>
    );
}
