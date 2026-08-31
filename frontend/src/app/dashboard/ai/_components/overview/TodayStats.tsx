"use client";

/**
 * overview/TodayStats.tsx — the TODAY snapshot row. Uses only fields already
 * served by GET /ai/dashboard (no backend change). Money via formatKES.
 */
import StatCard from "@/components/ui/StatCard";
import { formatKES, formatKESCompact } from "@/lib/format";
import type { QuickStats } from "./types";

export default function TodayStats({ qs }: { qs: QuickStats }) {
    const delta = qs.day_over_day_change || 0;
    return (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard
                label="Revenue today"
                value={formatKES(qs.today_revenue)}
                sub={
                    qs.yesterday_revenue > 0
                        ? `${delta >= 0 ? "Up" : "Down"} ${Math.abs(delta)}% vs yesterday`
                        : "No data from yesterday"
                }
                color={delta >= 0 ? "#22c55e" : "#ef4444"}
            />
            <StatCard
                label="Orders today"
                value={qs.today_orders}
                sub={qs.pending_orders ? `${qs.pending_orders} still being prepared` : "All caught up"}
                color="#d4a853"
            />
            <StatCard
                label="Average order"
                value={formatKES(qs.avg_order_value)}
                sub={`Across ${qs.menu_items || 0} menu items`}
                color="#3b82f6"
            />
            <StatCard
                label="Revenue · 30 days"
                value={formatKESCompact(qs.total_revenue_30d)}
                sub="Last 30 days"
                color="#a78bfa"
            />
        </div>
    );
}
