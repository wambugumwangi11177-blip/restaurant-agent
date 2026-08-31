"use client";

/**
 * overview/BusinessHealth.tsx — the health score made meaningful:
 *   43/100 → "Needs attention" → per-driver table → "what's affecting it" → act.
 * Reuses the shared HEALTH_ADVICE copy and the HowItWorks explainer.
 */
import { ArrowRight } from "lucide-react";
import { HowItWorks } from "@/components/ai/HowItWorks";
import {
    healthLabel,
    driverDot,
    driverText,
    worstDrivers,
    friendlyCategory,
    HEALTH_ADVICE,
    type HealthDriver,
} from "../healthAdvice";
import type { HealthBreakdownItem } from "./types";

function panelTone(score: number): string {
    if (score >= 75) return "border-success/30 bg-success/5";
    if (score >= 50) return "border-warning/30 bg-warning/5";
    return "border-danger/30 bg-danger/5";
}

export default function BusinessHealth({
    score,
    breakdown,
    onImprove,
}: {
    score: number;
    breakdown: HealthBreakdownItem[];
    onImprove: () => void;
}) {
    const worst = worstDrivers(breakdown as HealthDriver[], 2);

    return (
        <div className={`rounded-xl border p-5 ${panelTone(score)}`}>
            <div className="flex items-start justify-between gap-3">
                <div>
                    <p className="text-xs uppercase tracking-widest text-text-dim mb-1">Business health</p>
                    <p className={`text-5xl font-black leading-none ${driverText(score)}`}>
                        {score}
                        <span className="text-lg font-semibold text-text-dim"> /100</span>
                    </p>
                    <p className={`text-sm font-medium mt-1.5 ${driverText(score)}`}>{healthLabel(score)}</p>
                    <HowItWorks id="health" />
                </div>
            </div>

            {/* Driver table */}
            <div className="mt-4 space-y-2">
                {breakdown.map((b, i) => (
                    <div key={i} className="flex items-center gap-3">
                        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${driverDot(b.score)}`} />
                        <span className="text-xs text-text-muted w-24 flex-shrink-0">{friendlyCategory(b.category)}</span>
                        <div className="flex-1 h-1.5 bg-surface-hover rounded-full overflow-hidden">
                            <div
                                className={`h-full rounded-full ${driverDot(b.score)}`}
                                style={{ width: `${b.score}%` }}
                            />
                        </div>
                        <span className={`text-xs font-medium w-8 text-right ${driverText(b.score)}`}>{b.score}</span>
                    </div>
                ))}
            </div>

            {/* What's affecting your score */}
            {worst.length > 0 && (
                <div className="mt-4 pt-3 border-t border-border/60">
                    <p className="text-xs font-semibold text-text mb-1.5">What&apos;s affecting your score?</p>
                    <p className="text-xs text-text-dim mb-2">
                        {worst.map((w) => friendlyCategory(w.category)).join(" and ")}{" "}
                        {worst.length > 1 ? "are" : "is"} currently the biggest drag.
                    </p>
                    <div className="space-y-1.5">
                        {worst.map((w, i) => (
                            <p key={i} className="text-xs text-text-muted">
                                <span className="text-[var(--accent)]">→ </span>
                                {(HEALTH_ADVICE[w.category] || (() => "Review this area and act on the flagged items."))(w.detail)}
                            </p>
                        ))}
                    </div>
                </div>
            )}

            <button
                onClick={onImprove}
                className="mt-4 inline-flex items-center gap-1.5 text-xs font-medium text-[var(--accent)] hover:underline"
            >
                Improve health <ArrowRight className="w-3 h-3" />
            </button>
        </div>
    );
}
