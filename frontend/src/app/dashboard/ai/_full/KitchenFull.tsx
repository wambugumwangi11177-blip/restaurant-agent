"use client";

import { useAiModule } from "@/lib/useAiModule";
import { StatGrid, DataTable, SectionTitle, LoadingBlock } from "./shared";

interface KdsData {
    throughput: { total_completed?: number; orders_per_day?: number; items_per_day?: number; avg_prep_minutes?: number; median_completion_minutes?: number; p95_completion_minutes?: number; completion_rate?: number; stations_active?: number };
    station_performance?: Record<string, unknown>[];
    item_prep_times?: Record<string, unknown>[];
    bottlenecks: { station: string; avg_minutes: number; kitchen_avg: number; above_avg_by: number; severity: string; trend?: string }[];
    rush_periods: { label: string; is_rush: boolean; items_processed?: number; avg_prep_minutes?: number; load_factor?: number }[];
    efficiency_ratings?: Record<string, unknown>[];
    recommendations: { type?: string; message: string; action?: string; priority?: string }[];
}

export default function KitchenFull() {
    const { data, loading, error, retry } = useAiModule<KdsData>("/ai/kds-intelligence");
    if (loading) return <LoadingBlock />;
    if (error) return <div className="flex items-center gap-3"><p className="text-text-dim text-sm">{error}</p><button onClick={retry} className="px-3 py-1.5 rounded-lg bg-[var(--accent)] text-bg text-sm font-semibold">Retry</button></div>;
    if (!data) return null;
    const t = data.throughput ?? {};
    const autoTable = (rows: Record<string, unknown>[] | undefined, title: string, maxCols = 7) => {
        if (!rows?.length) return null;
        return (
            <>
                <SectionTitle>{title} ({rows.length})</SectionTitle>
                <DataTable
                    columns={Object.keys(rows[0]).slice(0, maxCols).map(k => ({ key: k, label: k.replace(/_/g, " ") }))}
                    rows={rows } />
            </>
        );
    };
    return (
        <div>
            <StatGrid stats={[
                { label: "Avg Prep", value: `${(t.avg_prep_minutes ?? 0).toFixed(1)} min` },
                { label: "Median Completion", value: `${t.median_completion_minutes ?? 0} min` },
                { label: "P95 Completion", value: `${t.p95_completion_minutes ?? 0} min` },
                { label: "Completion Rate", value: `${t.completion_rate ?? 0}%`, tone: (t.completion_rate ?? 0) >= 90 ? "ok" : "warn" },
            ]} />
            <SectionTitle>Bottlenecks</SectionTitle>
            <DataTable
                columns={[
                    { key: "station", label: "Station", render: r => <span className="capitalize">{String(r.station)}</span> },
                    { key: "avg_minutes", label: "Avg min" },
                    { key: "kitchen_avg", label: "Kitchen avg" },
                    { key: "above_avg_by", label: "Above by", render: r => <span className={r.severity === "high" ? "text-red-400" : "text-amber-400"}>+{String(r.above_avg_by)} min</span> },
                    { key: "severity", label: "Severity" },
                    { key: "trend", label: "Trend" },
                ]}
                rows={data.bottlenecks }
                empty="No bottlenecks — stations are balanced." />
            <SectionTitle>Rush-hour load (all hours)</SectionTitle>
            <DataTable
                columns={[
                    { key: "label", label: "Hour" },
                    { key: "items_processed", label: "Items" },
                    { key: "avg_prep_minutes", label: "Avg prep" },
                    { key: "load_factor", label: "Load" },
                    { key: "is_rush", label: "Rush?", render: r => r.is_rush ? <span className="text-amber-400 font-medium">rush</span> : "—" },
                ]}
                rows={data.rush_periods } />
            {autoTable(data.station_performance, "Station performance")}
            {autoTable(data.item_prep_times, "Per-item prep times")}
            {(data.recommendations?.length ?? 0) > 0 && (
                <>
                    <SectionTitle>Recommendations</SectionTitle>
                    <div className="space-y-2">
                        {data.recommendations.map((r, i) => (
                            <div key={i} className="p-3 rounded-lg bg-surface border border-surface-hover text-sm">
                                <p className="text-text">{r.message}</p>
                                {r.action && <p className="text-xs text-[var(--accent)] mt-1">💡 {r.action}</p>}
                            </div>
                        ))}
                    </div>
                </>
            )}
        </div>
    );
}
