"use client";

import { Zap, CheckCircle } from "lucide-react";

// Turns the health breakdown into specific, prioritised "do this next" guidance.
const HEALTH_ADVICE: Record<string, (detail: string) => string> = {
    "Menu Health": () => "Rework or remove your 'Dog' items and reprice 'Plowhorses' — see Menu Engineering below. Fewer weak items lifts this fast.",
    "Revenue Trend": () => "Revenue is trending down week-over-week. Run a promo on slow days and push high-margin items to reverse it.",
    "Kitchen Efficiency": () => "Prep times are dragging on the flagged stations. Rebalance staff to the bottleneck stations during peak hours.",
    "Inventory Status": () => "Restock the low items and use up near-expiry stock first (FIFO) to clear spoilage-risk flags.",
    "Reservation Reliability": () => "Cut no-shows with SMS reminders and a small deposit on large parties — that lifts completion and recovers lost covers.",
};

export default function HealthBoostSection({ breakdown, score }: { breakdown: { category: string; score: number; detail: string }[]; score: number }) {
    const weak = breakdown.filter((b) => b.score < 70).sort((a, b) => a.score - b.score);
    return (
        <div className="rounded-xl border border-[var(--accent)]/25 bg-[var(--accent)]/[0.04] p-5">
            <h2 className="text-sm font-semibold text-text mb-1 flex items-center gap-2">
                <Zap className="w-4 h-4 text-[var(--accent)]" />
                How to raise your health score ({score} → higher)
            </h2>
            <p className="text-xs text-text-dim mb-4">Your biggest wins first — each item below is dragging the score and is fixable.</p>
            {weak.length === 0 ? (
                <p className="text-emerald-400 text-sm flex items-center gap-2"><CheckCircle className="w-4 h-4" /> Every area is healthy — nice work.</p>
            ) : (
                <div className="space-y-2">
                    {weak.map((b, i) => (
                        <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-[#0f0f0f] border border-surface-hover">
                            <span className={`text-xs font-bold w-9 text-center flex-shrink-0 rounded px-1 py-0.5 ${b.score < 40 ? "bg-red-500/10 text-red-400" : "bg-amber-500/10 text-amber-400"}`}>{b.score}</span>
                            <div>
                                <p className="text-sm text-text font-medium">{b.category} <span className="text-text-dim font-normal">— {b.detail}</span></p>
                                <p className="text-xs text-[var(--accent)] mt-1">→ {(HEALTH_ADVICE[b.category] || (() => "Review this area's details and act on the flagged items."))(b.detail)}</p>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
