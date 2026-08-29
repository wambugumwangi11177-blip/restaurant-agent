"use client";

import { ChefHat } from "lucide-react";
import { useAiModule } from "@/lib/useAiModule";
import { MiniStat } from "@/components/ai/MiniStat";
import { ModuleShell } from "@/components/ai/ModuleShell";

interface KdsData {
    throughput: {
        avg_prep_minutes?: number;
        median_completion_minutes?: number;
        orders_per_day?: number;
        completion_rate?: number;
        stations_active?: number;
    };
    bottlenecks: { station: string; avg_minutes: number; kitchen_avg: number; above_avg_by: number; severity: string }[];
    rush_periods: { label: string; is_rush: boolean; items_processed?: number }[];
    recommendations: { message: string; action?: string }[];
}

export default function KdsSection() {
    const { data, loading, error, retry } = useAiModule<KdsData>("/ai/kds-intelligence");

    return (
        <ModuleShell
            icon={ChefHat}
            title="Kitchen Intelligence"
            subtitle="Actual prep times per station, bottlenecks, and rush-hour load from your kitchen display data."
            loading={loading}
            error={error}
            onRetry={retry}
            fullHref="/dashboard/ai/kitchen"
        >
            {data && (
                <>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                        <MiniStat label="Avg Prep" value={`${(data.throughput.avg_prep_minutes ?? 0).toFixed(1)} min`} />
                        <MiniStat label="Orders / Day" value={String(Math.round(data.throughput.orders_per_day ?? 0))} />
                        <MiniStat label="Completion" value={`${data.throughput.completion_rate ?? 0}%`} tone={(data.throughput.completion_rate ?? 0) >= 90 ? "ok" : "warn"} />
                        <MiniStat label="Active Stations" value={String(data.throughput.stations_active ?? 0)} />
                    </div>
                    {data.bottlenecks.length > 0 && (
                        <div className="space-y-1.5 mb-3">
                            {data.bottlenecks.slice(0, 3).map((b, i) => (
                                <div key={i} className="flex items-center justify-between gap-3 p-2.5 rounded-lg bg-surface border border-surface-hover text-sm">
                                    <span className="text-text capitalize">{b.station} station</span>
                                    <span className={b.severity === "high" ? "text-red-400" : "text-amber-400"}>
                                        {b.avg_minutes.toFixed(1)} min avg (+{b.above_avg_by.toFixed(1)} vs kitchen)
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}
                    {data.rush_periods?.some(r => r.is_rush) && (
                        <p className="text-text-dim text-xs mb-2">
                            Rush hours: {data.rush_periods.filter(r => r.is_rush).map(r => r.label).join(", ")}
                        </p>
                    )}
                    {data.recommendations.slice(0, 2).map((r, i) => (
                        <p key={i} className="text-xs text-[var(--accent)]">💡 {r.message}{r.action ? ` — ${r.action}` : ""}</p>
                    ))}
                </>
            )}
        </ModuleShell>
    );
}
