"use client";

/**
 * overview/PerformanceSection.tsx — Revenue + Orders trend lines. Fetches its
 * own data (GET /ai/revenue-forecast → daily_revenue) and draws both lines as
 * dependency-free Sparklines.
 */
import { useAiModule } from "@/lib/useAiModule";
import { Sparkline } from "@/components/ai/Sparkline";
import SectionCard from "@/components/ui/SectionCard";
import { formatKESCompact } from "@/lib/format";

interface DailyPoint {
    date: string;
    revenue: number;
    orders: number;
}
interface RevenueForecastLite {
    daily_revenue: DailyPoint[];
}

export default function PerformanceSection() {
    const { data, loading, error } = useAiModule<RevenueForecastLite>("/ai/revenue-forecast");
    const points = data?.daily_revenue ?? [];
    const latest = points.length > 0 ? points[points.length - 1] : null;

    return (
        <SectionCard title="Performance" subtitle="Revenue and orders — last 30 days">
            {loading && <div className="bg-surface-hover rounded-lg h-24 animate-pulse" />}

            {!loading && error && (
                <p className="text-xs text-text-dim">Trend data isn&apos;t available yet — record a few more orders.</p>
            )}

            {!loading && !error && points.length === 0 && (
                <p className="text-xs text-text-dim">No order history yet — trends appear once you start selling.</p>
            )}

            {!loading && !error && latest && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                        <div className="flex items-center justify-between mb-1">
                            <p className="text-xs text-text-dim">Revenue</p>
                            <p className="text-xs font-semibold text-success">{formatKESCompact(latest.revenue)}</p>
                        </div>
                        <Sparkline
                            values={points.map((p) => p.revenue)}
                            stroke="var(--success)"
                            ariaLabel="Revenue over the last 30 days"
                        />
                    </div>
                    <div>
                        <div className="flex items-center justify-between mb-1">
                            <p className="text-xs text-text-dim">Orders</p>
                            <p className="text-xs font-semibold text-info">{latest.orders}</p>
                        </div>
                        <Sparkline
                            values={points.map((p) => p.orders)}
                            stroke="var(--info)"
                            ariaLabel="Orders over the last 30 days"
                        />
                    </div>
                </div>
            )}
        </SectionCard>
    );
}
