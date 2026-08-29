"use client";

import type { OrderTrends, OrderForecastDay, OrderAnomaly } from "./types";

function formatKES(cents: number) {
    if (!cents) return "KES 0";
    return `KES ${(cents / 100).toLocaleString("en-KE", { maximumFractionDigits: 0 })}`;
}

function formatHour(hour: number) {
    if (hour === 0) return "12 midnight";
    if (hour === 12) return "12 noon";
    return hour > 12 ? `${hour - 12}pm` : `${hour}am`;
}

interface OrderInsightsPanelProps {
    trends: OrderTrends;
    forecast: OrderForecastDay[];
    anomalies: OrderAnomaly[];
}

/**
 * "What we're seeing" sales trends/forecast/anomalies card — pure display,
 * extracted from OrderList unmodified.
 */
export default function OrderInsightsPanel({ trends, forecast, anomalies }: OrderInsightsPanelProps) {
    const peakHour = trends.peak_hour;
    const peakDay = trends.peak_day;
    const wowGrowth = trends.week_over_week_growth;

    if (!(trends.total_revenue || forecast.length > 0)) return null;

    return (
        <div className="bg-surface border border-border rounded-xl">
            <div className="px-4 py-3 border-b border-surface-hover">
                <p className="text-xs font-semibold text-text">What we&apos;re seeing</p>
            </div>
            <div className="px-4 py-3 space-y-3">
                {/* Natural language insights */}
                <div className="space-y-2">
                    {trends.total_revenue > 0 && (
                        <p className="text-xs text-text-muted">
                            You&apos;ve made <span className="text-text font-semibold">{formatKES(trends.total_revenue)}</span> in the last 30 days
                        </p>
                    )}
                    {trends.avg_order_value > 0 && (
                        <p className="text-xs text-text-muted">
                            Customers spend about <span className="text-text font-semibold">{formatKES(trends.avg_order_value)}</span> per order on average
                        </p>
                    )}
                    {wowGrowth !== undefined && wowGrowth !== 0 && (
                        <p className="text-xs text-text-muted">
                            Compared to last week, sales are{" "}
                            <span className={`font-semibold ${wowGrowth >= 0 ? "text-success" : "text-danger"}`}>
                                {wowGrowth > 0 ? "up" : "down"} {Math.abs(wowGrowth).toFixed(1)}%
                            </span>
                        </p>
                    )}
                    {peakDay && (
                        <p className="text-xs text-text-muted">
                            Your busiest day is usually <span className="text-accent font-semibold">{peakDay}</span>
                            {peakHour !== undefined && (
                                <>, and the rush comes around <span className="text-accent font-semibold">{formatHour(peakHour)}</span></>
                            )}
                        </p>
                    )}
                </div>

                {/* Next 7 days forecast */}
                {forecast.length > 0 && (
                    <div>
                        <p className="text-[10px] text-text-dim mb-2">Expected sales this coming week</p>
                        <div className="flex gap-1 items-end h-14">
                            {forecast.map((f, i: number) => {
                                const max = Math.max(...forecast.map((ff) => ff.predicted || ff.amount || 0));
                                const val = f.predicted || f.amount || 0;
                                const pct = max > 0 ? (val / max) * 100 : 0;
                                return (
                                    <div key={i} className="flex-1 flex flex-col items-center gap-1">
                                        <div className="w-full rounded-sm relative overflow-hidden" style={{ height: `${Math.max(pct, 8)}%` }}>
                                            <div className="absolute inset-0 bg-accent/30 rounded-sm" />
                                        </div>
                                        <span className="text-[8px] text-text-dim">{f.day_name?.slice(0, 3) || `Day ${i + 1}`}</span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}

                {/* Unusual days */}
                {anomalies.length > 0 && (
                    <div className="space-y-1 pt-2 border-t border-surface-hover">
                        <p className="text-[10px] text-text-dim uppercase tracking-wider">Unusual days we noticed</p>
                        {anomalies.slice(0, 2).map((a, i: number) => (
                            <p key={i} className="text-xs text-text-muted">
                                {a.date}: sales were{" "}
                                <span className={a.type === "high" ? "text-success" : "text-danger"}>
                                    {a.type === "high" ? "higher than normal" : "lower than usual"}
                                </span>
                                {" "}at {formatKES(a.revenue)}
                            </p>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
