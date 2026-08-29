"use client";

import { useAiModule } from "@/lib/useAiModule";
import { StatGrid, DataTable, SectionTitle, money, LoadingBlock } from "./shared";

interface ResData {
    no_show_analysis: { total_reservations?: number; no_shows?: number; no_show_rate?: number; cancellations?: number; cancel_rate?: number; completion_rate?: number; no_show_by_day?: { day: string; total_bookings: number; no_shows: number; no_show_rate: number; completion_rate: number }[] };
    revenue_impact?: Record<string, unknown>;
    table_utilization?: Record<string, unknown>[];
    revpash?: Record<string, unknown>;
    lead_time_analysis?: Record<string, unknown>[];
    party_size_analysis?: Record<string, unknown>[];
    peak_windows?: Record<string, unknown>[];
    overbooking?: Record<string, unknown>;
    recommendations: { message?: string; action?: string }[];
}

export default function ReservationsFull() {
    const { data, loading, error, retry } = useAiModule<ResData>("/ai/reservation-insights");
    if (loading) return <LoadingBlock />;
    if (error) return <div className="flex items-center gap-3"><p className="text-text-dim text-sm">{error}</p><button onClick={retry} className="px-3 py-1.5 rounded-lg bg-[var(--accent)] text-bg text-sm font-semibold">Retry</button></div>;
    if (!data) return null;
    const ns = data.no_show_analysis ?? {};
    const autoTable = (rows: Record<string, unknown>[] | undefined, title: string, maxCols = 6) => {
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
    const kvBlock = (obj: Record<string, unknown> | undefined, title: string) => {
        if (!obj || !Object.keys(obj).length) return null;
        const entries = Object.entries(obj).filter(([, v]) => typeof v !== "object" || v === null);
        if (!entries.length) return null;
        return (
            <>
                <SectionTitle>{title}</SectionTitle>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {entries.map(([k, v]) => (
                        <div key={k} className="rounded-xl border border-surface-hover bg-[#0f0f0f] p-3">
                            <p className="text-xs text-text-dim mb-1">{k.replace(/_/g, " ")}</p>
                            <p className="text-sm font-bold text-text">{typeof v === "number" && /cents|revenue|amount|impact/.test(k) ? money(v) : String(v)}</p>
                        </div>
                    ))}
                </div>
            </>
        );
    };
    return (
        <div>
            <StatGrid stats={[
                { label: "Reservations", value: String(ns.total_reservations ?? 0) },
                { label: "No-show Rate", value: `${ns.no_show_rate ?? 0}%`, tone: (ns.no_show_rate ?? 0) > 10 ? "warn" : "ok" },
                { label: "Completion Rate", value: `${ns.completion_rate ?? 0}%` },
                { label: "Cancellations", value: `${ns.cancellations ?? 0} (${ns.cancel_rate ?? 0}%)` },
            ]} />
            {autoTable(ns.no_show_by_day, "No-shows by day of week")}
            {kvBlock(data.revenue_impact, "Revenue impact")}
            {kvBlock(data.revpash, "Revenue per seat per hour (RevPASH)")}
            {kvBlock(data.overbooking, "Overbooking strategy")}
            {autoTable(data.table_utilization, "Table utilization")}
            {autoTable(data.lead_time_analysis, "Booking lead time")}
            {autoTable(data.party_size_analysis, "Party sizes")}
            {autoTable(data.peak_windows, "Peak windows")}
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
