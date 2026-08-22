"use client";

import { useAiModule } from "@/lib/useAiModule";
import { StatGrid, DataTable, SectionTitle, money, LoadingBlock } from "./shared";

interface ProfitData {
    narrative?: { text?: string } | string | null;
    summary: { food_cost_pct?: number; gross_margin_pct?: number; profit_leaks_found?: number; total_leak_amount?: number; total_gross_profit_30d_cents?: number };
    contribution_margins: Record<string, unknown>[];
    profit_leaks: Record<string, unknown>[];
    daypart_analysis: Record<string, unknown>[];
    channel_analysis: Record<string, unknown>[];
    customer_intelligence?: Record<string, unknown>;
    upsell_uplift: Record<string, unknown>[];
    profit_forecast?: Record<string, unknown>;
    portion_drift: Record<string, unknown>[];
}

export default function ProfitFull() {
    const { data, loading, error, retry } = useAiModule<ProfitData>("/ai/profit?narrate=true");
    if (loading) return <LoadingBlock />;
    if (error) return <div className="flex items-center gap-3"><p className="text-text-dim text-sm">{error}</p><button onClick={retry} className="px-3 py-1.5 rounded-lg bg-[var(--accent)] text-bg text-sm font-semibold">Retry</button></div>;
    if (!data) return null;
    const s = data.summary ?? {};
    const autoTable = (rows: Record<string, unknown>[], title: string, empty?: string, maxCols = 8) => (
        <>
            <SectionTitle>{title} ({rows?.length ?? 0})</SectionTitle>
            <DataTable
                columns={Object.keys(rows?.[0] ?? { a: "" }).slice(0, maxCols).map(k => ({ key: k, label: k.replace(/_/g, " ") }))}
                rows={(rows ?? []) }
                empty={empty ?? "Nothing flagged."} />
        </>
    );
    return (
        <div>
            <StatGrid stats={[
                { label: "Gross Margin", value: `${s.gross_margin_pct ?? 0}%`, tone: (s.gross_margin_pct ?? 0) >= 55 ? "ok" : "warn" },
                { label: "Food Cost", value: `${s.food_cost_pct ?? 0}%`, tone: (s.food_cost_pct ?? 0) <= 35 ? "ok" : "warn" },
                { label: "Profit Leaks", value: String(s.profit_leaks_found ?? 0), tone: (s.profit_leaks_found ?? 0) > 0 ? "warn" : "ok" },
                { label: "Leak Amount", value: money(s.total_leak_amount) },
            ]} />
            {data.narrative && (
                <div className="rounded-xl border border-[var(--accent)]/20 bg-[var(--accent)]/5 p-4 mb-2 text-sm text-text">{typeof data.narrative === "string" ? data.narrative : data.narrative.text || ""}</div>
            )}
            {autoTable(data.contribution_margins, "Contribution margins — every item")}
            {autoTable(data.profit_leaks, "Profit leaks")}
            {autoTable(data.daypart_analysis, "Profitability by daypart")}
            {autoTable(data.channel_analysis, "Profitability by channel")}
            {data.customer_intelligence && Object.keys(data.customer_intelligence).length > 0 && autoTable(
                Array.isArray(data.customer_intelligence) ? data.customer_intelligence : [data.customer_intelligence], "Customer intelligence")}
            {autoTable(data.upsell_uplift, "Upsell uplift opportunities")}
            {autoTable(data.portion_drift, "Portion drift")}
        </div>
    );
}
