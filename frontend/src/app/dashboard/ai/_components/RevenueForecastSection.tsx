"use client";

import { TrendingUp } from "lucide-react";
import { formatKES, formatKESCompact } from "@/lib/format";
import { useAiModule } from "@/lib/useAiModule";
import { MiniStat } from "@/components/ai/MiniStat";
import { ModuleShell } from "@/components/ai/ModuleShell";

interface RevenueForecastData {
    forecast: {
        date: string;
        day: string;
        predicted_revenue: number;
        confidence_low: number;
        confidence_high: number;
        confidence_pct: number;
    }[];
    trends: {
        total_revenue: number;
        avg_daily_revenue: number;
        week_over_week_growth: number;
        month_over_month_growth: number;
    };
}

export default function RevenueForecastSection() {
    const { data, loading, error, retry } = useAiModule<RevenueForecastData>("/ai/revenue-forecast");

    return (
        <ModuleShell
            icon={TrendingUp}
            title="Revenue Forecast"
            subtitle="Next 7 days predicted from your own sales pattern — with confidence bands."
            loading={loading}
            error={error}
            onRetry={retry}
        >
            {data && (
                <>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                        <MiniStat label="30-Day Revenue" value={formatKESCompact(data.trends.total_revenue)} />
                        <MiniStat label="Avg / Day" value={formatKESCompact(data.trends.avg_daily_revenue)} />
                        <MiniStat
                            label="WoW Growth"
                            value={`${data.trends.week_over_week_growth >= 0 ? "+" : ""}${data.trends.week_over_week_growth}%`}
                            tone={data.trends.week_over_week_growth >= 0 ? "ok" : "warn"}
                        />
                        <MiniStat
                            label="MoM Growth"
                            value={`${data.trends.month_over_month_growth >= 0 ? "+" : ""}${data.trends.month_over_month_growth}%`}
                            tone={data.trends.month_over_month_growth >= 0 ? "ok" : "warn"}
                        />
                    </div>
                    {data.forecast.length === 0 ? (
                        <p className="text-text-dim text-sm">Not enough sales history to forecast yet.</p>
                    ) : (
                        <div className="space-y-1.5">
                            {data.forecast.slice(0, 7).map((f) => (
                                <div key={f.date} className="flex items-center justify-between gap-3 p-2.5 rounded-lg bg-surface border border-surface-hover text-sm">
                                    <span className="text-text w-28 shrink-0">
                                        {f.day}
                                        <span className="text-text-dim text-xs ml-1.5">{f.date.slice(5)}</span>
                                    </span>
                                    <span className="text-text font-semibold">{formatKES(f.predicted_revenue)}</span>
                                    <span className="text-text-dim text-xs text-right hidden sm:block">
                                        range {formatKESCompact(f.confidence_low)} – {formatKESCompact(f.confidence_high)}
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}
                </>
            )}
        </ModuleShell>
    );
}
