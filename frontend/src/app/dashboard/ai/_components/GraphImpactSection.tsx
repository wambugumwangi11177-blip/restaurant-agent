"use client";

import { useEffect, useState } from "react";
import { Network } from "lucide-react";
import api from "@/lib/api";
import { formatKESCompact } from "@/lib/format";
import { ModuleShell } from "@/components/ai/ModuleShell";

interface InventoryItem { id: number; item_name: string; unit?: string }
interface ImpactData {
    available?: boolean;
    error?: string;
    root?: { label: string };
    summary?: {
        affected_dishes: number;
        critical_dishes: number;
        affected_categories: number;
        revenue_at_risk_30d_cents: number;
    };
    affected?: Record<string, { label?: string; type?: string }[]>;
}

export default function GraphImpactSection() {
    const [items, setItems] = useState<InventoryItem[]>([]);
    const [selected, setSelected] = useState<number | null>(null);
    const [impact, setImpact] = useState<ImpactData | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    useEffect(() => {
        api.get("/inventory/").then(res => {
            const list: InventoryItem[] = (res.data ?? []).map((i: InventoryItem) => ({ id: i.id, item_name: i.item_name, unit: i.unit }));
            setItems(list);
            if (list.length) setSelected(list[0].id);
        }).catch(() => setError("Could not load stock items"));
    }, []);

    useEffect(() => {
        if (selected == null) return;
        setLoading(true);
        setError("");
        api.get(`/ai/graph/impact`, { params: { entity: "ingredient", id: selected } })
            .then(res => setImpact(res.data))
            .catch(() => setError("Impact lookup failed"))
            .finally(() => setLoading(false));
    }, [selected]);

    const s = impact?.summary;

    return (
        <ModuleShell
            icon={Network}
            title="Impact Cascade (Knowledge Graph)"
            subtitle="Pick an ingredient — see every dish it feeds, its categories, and how much revenue is at risk if it runs out."
            loading={loading}
            error={error}
            onRetry={() => setSelected(selected)}
        >
            <div className="mb-4">
                <select
                    aria-label="Ingredient"
                    className="w-full sm:w-72 bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text"
                    value={selected ?? ""}
                    onChange={e => setSelected(Number(e.target.value))}
                >
                    {items.map(i => (
                        <option key={i.id} value={i.id}>{i.item_name}</option>
                    ))}
                </select>
            </div>
            {impact && s && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="p-3 rounded-lg bg-surface border border-surface-hover">
                        <p className="text-xs text-text-dim mb-1">Affected Dishes</p>
                        <p className="text-xl font-bold text-text">{s.affected_dishes}</p>
                    </div>
                    <div className="p-3 rounded-lg bg-surface border border-surface-hover">
                        <p className="text-xs text-text-dim mb-1">Critical (can&apos;t skip)</p>
                        <p className="text-xl font-bold text-text">{s.critical_dishes}</p>
                    </div>
                    <div className="p-3 rounded-lg bg-surface border border-surface-hover">
                        <p className="text-xs text-text-dim mb-1">Categories</p>
                        <p className="text-xl font-bold text-text">{s.affected_categories}</p>
                    </div>
                    <div className="p-3 rounded-lg bg-surface border border-surface-hover">
                        <p className="text-xs text-text-dim mb-1">Revenue at Risk (30d)</p>
                        <p className={`text-xl font-bold ${s.revenue_at_risk_30d_cents > 0 ? "text-amber-400" : "text-text"}`}>
                            {formatKESCompact(s.revenue_at_risk_30d_cents)}
                        </p>
                    </div>
                </div>
            )}
            {impact && s && s.affected_dishes === 0 && (
                <p className="text-text-dim text-xs mt-3">
                    No dishes linked to this ingredient yet — add it to recipes via Menu → item → ingredients to see cascades.
                </p>
            )}
        </ModuleShell>
    );
}
