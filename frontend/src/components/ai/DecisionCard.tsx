"use client";

/**
 * frontend/src/components/ai/DecisionCard.tsx
 * One ranked Decision, rendered in the AI Command Center's dark theme. Mirrors
 * the backend `Decision.to_dict()` shape from ai/decisions/model.py + ranking.py.
 *
 * The three star meters map straight to the backend's ordinals:
 *   Impact  = impact_stars   (0..5, 0 when the agent didn't quantify money)
 *   Ease    = ease_stars     (6 - difficulty; more = easier)
 *   Safety  = 6 - risk_stars (invert risk so more = safer, consistent "more is better")
 */

import { ExplainButton } from "./ExplainButton";
import { formatKES } from "@/lib/format";

export interface Decision {
    agent: string;
    category: string;
    action: string;
    rationale: string;
    confidence_pct: number;
    risk: number;
    difficulty: number;
    impact_cents_month: number | null;
    quantified: boolean;
    data_sources: string[];
    alternatives: string[];
    priority_score: number;
    impact_stars: number;
    risk_stars: number;
    ease_stars: number;
    rank: number;
    meta?: Record<string, unknown>;
}

function Stars({ filled, tone }: { filled: number; tone: string }) {
    return (
        <span className="inline-flex gap-0.5" aria-hidden>
            {[1, 2, 3, 4, 5].map((i) => (
                <span
                    key={i}
                    className={`w-1.5 h-1.5 rounded-full ${i <= filled ? tone : "bg-[#262626]"}`}
                />
            ))}
        </span>
    );
}

function Meter({ label, filled, tone }: { label: string; filled: number; tone: string }) {
    return (
        <div className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wide text-[#7e7e7e]">{label}</span>
            <Stars filled={filled} tone={tone} />
        </div>
    );
}

const categoryTone: Record<string, string> = {
    pricing: "text-[#d4a853] bg-[#d4a853]/10",
    inventory: "text-[#60a5fa] bg-[#3b82f6]/10",
    supply_chain: "text-[#a78bfa] bg-[#8b5cf6]/10",
    marketing: "text-[#f472b6] bg-[#ec4899]/10",
    menu: "text-emerald-400 bg-emerald-500/10",
    labor: "text-orange-400 bg-orange-500/10",
};

export function DecisionCard({ d, highlight = false }: { d: Decision; highlight?: boolean }) {
    return (
        <div
            className={`rounded-lg border p-4 ${
                highlight ? "border-[#d4a853]/40 bg-[#d4a853]/[0.04]" : "border-[#1a1a1a] bg-[#0f0f0f]"
            }`}
        >
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                        <span className="text-[10px] font-bold text-[#0a0a0a] bg-[#d4a853] rounded px-1.5 py-0.5">
                            #{d.rank}
                        </span>
                        <span className={`text-[10px] font-medium uppercase tracking-wide px-1.5 py-0.5 rounded ${categoryTone[d.category] || "text-[#8a8a8a] bg-[#141414]"}`}>
                            {d.category.replace("_", " ")}
                        </span>
                        <span className="text-[10px] text-[#7e7e7e]">{d.confidence_pct}% confidence</span>
                    </div>
                    <p className="text-sm text-[#e5e5e5] font-medium">{d.action}</p>
                    <p className="text-xs text-[#7e7e7e] mt-0.5">{d.rationale}</p>
                    <ExplainButton item={d} label={`${d.category} decision: ${d.action}`} />
                </div>
                <div className="text-right flex-shrink-0">
                    <p className="text-lg font-black text-[#e5e5e5] leading-none">{d.priority_score}</p>
                    <p className="text-[10px] text-[#7e7e7e]">priority</p>
                    {d.quantified && d.impact_cents_month ? (
                        <p className="text-emerald-400 text-xs font-medium mt-1 whitespace-nowrap">
                            +{formatKES(d.impact_cents_month)}/mo
                        </p>
                    ) : null}
                </div>
            </div>

            <div className="flex gap-5 mt-3 pt-3 border-t border-[#1a1a1a]">
                <Meter label="Impact" filled={d.impact_stars} tone="bg-emerald-400" />
                <Meter label="Ease" filled={d.ease_stars} tone="bg-[#60a5fa]" />
                <Meter label="Safety" filled={6 - d.risk_stars} tone="bg-[#d4a853]" />
            </div>
        </div>
    );
}
