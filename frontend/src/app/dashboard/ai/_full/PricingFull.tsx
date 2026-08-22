"use client";

import { useAiModule } from "@/lib/useAiModule";
import { StatGrid, DataTable, SectionTitle, money } from "./shared";
import { LoadingBlock } from "./shared";

interface Rec { id: number; item_name: string; type?: string; current_price?: number; suggested_price?: number; monthly_impact_cents?: number; reason?: string; status?: string }
interface PricingData {
    narrative?: { text?: string } | string | null;
    summary: { items_analysed?: number; reprice_needed?: number; surge_opportunities?: number; stimulate_candidates?: number; total_revenue_opportunity_cents?: number };
    recommendations: Rec[];
    delivery_gaps: Record<string, unknown>[];
    item_analyses: Record<string, unknown>[];
}

export default function PricingFull() {
    const { data, loading, error, retry } = useAiModule<PricingData>("/ai/pricing?narrate=true");
    if (loading) return <LoadingBlock />;
    if (error) return <div className="flex items-center gap-3"><p className="text-text-dim text-sm">{error}</p><button onClick={retry} className="px-3 py-1.5 rounded-lg bg-[var(--accent)] text-bg text-sm font-semibold">Retry</button></div>;
    if (!data) return null;
    const s = data.summary ?? {};
    return (
        <div>
            <StatGrid stats={[
                { label: "Items Analysed", value: String(s.items_analysed ?? 0) },
                { label: "Reprice Needed", value: String(s.reprice_needed ?? 0), tone: (s.reprice_needed ?? 0) > 0 ? "warn" : "ok" },
                { label: "Surge Opportunities", value: String(s.surge_opportunities ?? 0) },
                { label: "Revenue Opportunity", value: money(s.total_revenue_opportunity_cents), tone: "ok" },
            ]} />
            {data.narrative && (
                <div className="rounded-xl border border-[var(--accent)]/20 bg-[var(--accent)]/5 p-4 mb-2 text-sm text-text">{typeof data.narrative === "string" ? data.narrative : data.narrative.text || ""}</div>
            )}
            <SectionTitle>All recommendations ({data.recommendations.length})</SectionTitle>
            <DataTable
                columns={[
                    { key: "item_name", label: "Item" },
                    { key: "type", label: "Type" },
                    { key: "current_price", label: "Current", render: r => money(r.current_price as number) },
                    { key: "suggested_price", label: "Suggested", render: r => money(r.suggested_price as number) },
                    { key: "monthly_impact_cents", label: "Impact / mo", render: r => money(r.monthly_impact_cents as number) },
                    { key: "reason", label: "Reason" },
                    { key: "status", label: "Status" },
                ]}
                rows={data.recommendations }
                empty="No pricing recommendations right now." />
            <SectionTitle>Delivery-channel gaps</SectionTitle>
            <DataTable
                columns={Object.keys(data.delivery_gaps?.[0] ?? { channel: "" }).map(k => ({ key: k, label: k.replace(/_/g, " ") }))}
                rows={data.delivery_gaps }
                empty="No delivery gaps detected." />
            <SectionTitle>Per-item analyses ({data.item_analyses.length})</SectionTitle>
            <DataTable
                columns={Object.keys(data.item_analyses?.[0] ?? { item: "" }).slice(0, 8).map(k => ({ key: k, label: k.replace(/_/g, " ") }))}
                rows={data.item_analyses }
                empty="No item analyses." />
        </div>
    );
}
