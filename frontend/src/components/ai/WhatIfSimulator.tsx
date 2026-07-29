"use client";

/**
 * frontend/src/components/ai/WhatIfSimulator.tsx
 * "What if…" panel — pick a dish, propose a new price (or a promo discount), and
 * see the deterministic projection from POST /ai/simulate: sales, profit, margin
 * and a satisfaction proxy, with a YES/CAUTION/NO verdict and confidence.
 *
 * All numbers come from the backend simulation engine — this component only
 * renders them; it computes nothing itself.
 */

import { useEffect, useState } from "react";
import { FlaskConical } from "lucide-react";
import api from "@/lib/api";
import { formatKES } from "@/lib/format";
import { HowItWorks } from "./HowItWorks";

interface MenuItem { id: number; name: string; price: number; cost_price?: number; category?: string; }

interface SimResult {
    available: boolean;
    error?: string;
    change?: { new_price: number; price_change_pct: number };
    projected?: { monthly_profit_cents: number; margin_pct: number };
    deltas?: {
        sales_pct: number; profit_cents_month: number;
        margin_pct_points: number; satisfaction_pct_points: number;
    };
    confidence_pct?: number;
    verdict?: "YES" | "CAUTION" | "NO";
    verdict_reason?: string;
    assumptions?: string[];
}

const verdictStyle: Record<string, string> = {
    YES: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
    CAUTION: "bg-amber-500/15 text-amber-400 border-amber-500/30",
    NO: "bg-red-500/15 text-red-400 border-red-500/30",
};

function Delta({ label, value, good }: { label: string; value: string; good: boolean }) {
    return (
        <div className="rounded-lg border border-[#1a1a1a] bg-[#0a0a0a] p-3">
            <p className="text-[10px] uppercase tracking-wide text-[#7e7e7e]">{label}</p>
            <p className={`text-sm font-semibold ${good ? "text-emerald-400" : "text-red-400"}`}>{value}</p>
        </div>
    );
}

export function WhatIfSimulator() {
    const [items, setItems] = useState<MenuItem[]>([]);
    const [itemId, setItemId] = useState<number | null>(null);
    const [newPrice, setNewPrice] = useState<string>("");
    const [result, setResult] = useState<SimResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    useEffect(() => {
        api.get("/menu").then((r) => {
            const list: MenuItem[] = r.data || [];
            setItems(list);
            if (list.length) {
                setItemId(list[0].id);
                setNewPrice(String(list[0].price));
            }
        }).catch(() => setError("Could not load your menu."));
    }, []);

    const selected = items.find((i) => i.id === itemId);

    const onSelect = (id: number) => {
        setItemId(id);
        const it = items.find((i) => i.id === id);
        if (it) setNewPrice(String(it.price));
        setResult(null);
    };

    const runSim = async () => {
        if (itemId == null || !newPrice) return;
        setLoading(true);
        setError("");
        try {
            const res = await api.post("/ai/simulate", {
                change: { type: "price_change", item_id: itemId, new_price: Math.round(Number(newPrice)) },
            });
            if (res.data?.available === false) setError(res.data.error || "Simulation unavailable.");
            else setResult(res.data);
        } catch (e: any) {
            setError(e?.response?.data?.detail || e?.message || "Simulation failed.");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
            <h2 className="text-sm font-semibold text-[#e5e5e5] flex items-center gap-2">
                <FlaskConical className="w-4 h-4 text-[#d4a853]" />
                What-If Simulator
            </h2>
            <p className="text-xs text-[#7e7e7e] mt-1">
                Test a price change before you make it — projected on your own sales history.
            </p>
            <HowItWorks id="simulate" />
            <div className="mb-4" />

            <div className="flex flex-wrap items-end gap-3">
                <label className="flex flex-col gap-1">
                    <span className="text-[10px] uppercase tracking-wide text-[#7e7e7e]">Dish</span>
                    <select
                        value={itemId ?? ""}
                        onChange={(e) => onSelect(Number(e.target.value))}
                        className="bg-[#0a0a0a] border border-[#262626] rounded-lg text-sm text-[#e5e5e5] px-3 py-2 min-w-[160px]"
                    >
                        {items.map((i) => (
                            <option key={i.id} value={i.id}>{i.name}</option>
                        ))}
                    </select>
                </label>
                <label className="flex flex-col gap-1">
                    <span className="text-[10px] uppercase tracking-wide text-[#7e7e7e]">
                        New price (cents){selected ? ` — now KES ${(selected.price / 100).toLocaleString()}` : ""}
                    </span>
                    <input
                        type="number"
                        value={newPrice}
                        onChange={(e) => setNewPrice(e.target.value)}
                        className="bg-[#0a0a0a] border border-[#262626] rounded-lg text-sm text-[#e5e5e5] px-3 py-2 w-40"
                    />
                </label>
                <button
                    onClick={runSim}
                    disabled={loading || itemId == null}
                    className="bg-[#d4a853] text-[#0a0a0a] font-medium text-sm px-4 py-2 rounded-lg hover:opacity-90 disabled:opacity-40 transition-opacity"
                >
                    {loading ? "Simulating…" : "Simulate"}
                </button>
            </div>

            {error && <p className="text-red-400 text-sm mt-3">{error}</p>}

            {result?.available && result.deltas && (
                <div className="mt-4 space-y-3">
                    <div className="flex items-center gap-3 flex-wrap">
                        <span className={`text-xs font-bold px-2.5 py-1 rounded-md border ${verdictStyle[result.verdict || "CAUTION"]}`}>
                            {result.verdict}
                        </span>
                        <span className="text-xs text-[#8a8a8a]">{result.verdict_reason}</span>
                        <span className="text-xs text-[#7e7e7e] ml-auto">{result.confidence_pct}% confidence</span>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        <Delta label="Sales" value={`${result.deltas.sales_pct > 0 ? "+" : ""}${result.deltas.sales_pct}%`} good={result.deltas.sales_pct >= 0} />
                        <Delta label="Profit / mo" value={`${result.deltas.profit_cents_month >= 0 ? "+" : ""}${formatKES(result.deltas.profit_cents_month)}`} good={result.deltas.profit_cents_month >= 0} />
                        <Delta label="Margin" value={`${result.deltas.margin_pct_points >= 0 ? "+" : ""}${result.deltas.margin_pct_points} pts`} good={result.deltas.margin_pct_points >= 0} />
                        <Delta label="Satisfaction" value={`${result.deltas.satisfaction_pct_points >= 0 ? "+" : ""}${result.deltas.satisfaction_pct_points} pts`} good={result.deltas.satisfaction_pct_points >= 0} />
                    </div>
                    {result.assumptions && (
                        <ul className="text-[11px] text-[#7e7e7e] space-y-0.5 pt-1">
                            {result.assumptions.map((a, i) => <li key={i}>• {a}</li>)}
                        </ul>
                    )}
                </div>
            )}
        </div>
    );
}
