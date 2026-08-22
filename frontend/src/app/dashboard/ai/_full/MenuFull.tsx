"use client";

import { useAiModule } from "@/lib/useAiModule";
import { StatGrid, DataTable, SectionTitle, money, LoadingBlock } from "./shared";

interface MatrixItem { id: number; name: string; category: string; price: number; cost_price?: number; margin_pct?: number; food_cost_pct?: number; qty_sold: number; revenue: number; contribution?: number; classification: string; trend?: string; trend_pct?: number }
interface MenuData {
    summary: { total_items?: number; stars?: number; plowhorses?: number; puzzles?: number; dogs?: number; avg_food_cost_pct?: number };
    matrix: MatrixItem[];
    category_performance: Record<string, unknown>[];
    pareto?: Record<string, unknown>[];
    recommendations: { message?: string; action?: string }[];
    upsell_pairs?: Record<string, unknown>[];
}

const clsTone = (c: string) =>
    c === "Star" ? "text-emerald-400" : c === "Dog" ? "text-red-400" : c === "Puzzle" ? "text-amber-400" : "text-text";

export default function MenuFull() {
    const { data, loading, error, retry } = useAiModule<MenuData>("/ai/menu-engineering?narrate=true");
    if (loading) return <LoadingBlock />;
    if (error) return <div className="flex items-center gap-3"><p className="text-text-dim text-sm">{error}</p><button onClick={retry} className="px-3 py-1.5 rounded-lg bg-[var(--accent)] text-bg text-sm font-semibold">Retry</button></div>;
    if (!data) return null;
    const s = data.summary ?? {};
    const sorted = [...(data.matrix ?? [])].sort((a, b) => (b.revenue ?? 0) - (a.revenue ?? 0));
    return (
        <div>
            <StatGrid stats={[
                { label: "Items", value: String(s.total_items ?? data.matrix.length) },
                { label: "Stars", value: String(s.stars ?? 0), tone: "ok" },
                { label: "Puzzles (promote)", value: String(s.puzzles ?? 0), tone: "warn" },
                { label: "Dogs (cut)", value: String(s.dogs ?? 0), tone: "bad" },
            ]} />
            <SectionTitle>Full matrix — every dish by revenue</SectionTitle>
            <DataTable
                columns={[
                    { key: "name", label: "Dish" },
                    { key: "category", label: "Category" },
                    { key: "classification", label: "Class", render: r => <span className={`font-medium ${clsTone(String(r.classification))}`}>{String(r.classification)}</span> },
                    { key: "price", label: "Price", render: r => money(r.price as number) },
                    { key: "food_cost_pct", label: "Food cost", render: r => `${r.food_cost_pct ?? "—"}%` },
                    { key: "qty_sold", label: "Sold (30d)" },
                    { key: "revenue", label: "Revenue", render: r => money(r.revenue as number) },
                    { key: "trend", label: "Trend", render: r => `${r.trend ?? "—"}${r.trend_pct != null ? ` (${r.trend_pct}%)` : ""}` },
                ]}
                rows={sorted } />
            <SectionTitle>Category performance</SectionTitle>
            <DataTable
                columns={Object.keys(data.category_performance?.[0] ?? { category: "" }).map(k => ({ key: k, label: k.replace(/_/g, " ") }))}
                rows={data.category_performance }
                empty="No categories." />
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
