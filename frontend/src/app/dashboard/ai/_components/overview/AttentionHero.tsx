"use client";

/**
 * overview/AttentionHero.tsx — the "Needs attention" hero. Replaces the bare
 * "Active Alerts: 13" number with grouped counts and a short ranked list where
 * every row has a concrete next step (Reorder / Investigate / Review).
 */
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import SectionCard from "@/components/ui/SectionCard";
import { ExplainButton } from "@/components/ai/ExplainButton";
import {
    type AttentionItem,
    groupCounts,
    CLASS_CHIP,
    CLASS_DOT,
    CLASS_EDGE,
    CLASS_LABEL,
} from "./taxonomy";
import { actionFor } from "./actions";

export default function AttentionHero({
    items,
    onViewAll,
}: {
    items: AttentionItem[];
    onViewAll: () => void;
}) {
    const counts = groupCounts(items);
    // Hero shows the urgent/interesting items; plain "information" stays in Insights.
    const heroItems = items.filter((i) => i.cls !== "information").slice(0, 5);

    return (
        <SectionCard
            title="Needs attention"
            subtitle="The few things worth your time right now — each with a next step."
            action={
                <button
                    onClick={onViewAll}
                    className="flex items-center gap-1 text-xs text-[var(--accent)] hover:underline"
                >
                    View all <ArrowRight className="w-3 h-3" />
                </button>
            }
        >
            <div className="flex flex-wrap items-center gap-2 mb-4">
                <span className={`flex items-center gap-1.5 text-xs font-semibold px-2 py-1 rounded-md ${CLASS_CHIP.critical}`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${CLASS_DOT.critical}`} />
                    {counts.critical} Critical
                </span>
                <span className={`flex items-center gap-1.5 text-xs font-semibold px-2 py-1 rounded-md ${CLASS_CHIP.warning}`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${CLASS_DOT.warning}`} />
                    {counts.warning} Warning
                </span>
                <span className={`flex items-center gap-1.5 text-xs font-semibold px-2 py-1 rounded-md ${CLASS_CHIP.opportunity}`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${CLASS_DOT.opportunity}`} />
                    {counts.opportunity} Opportunities
                </span>
            </div>

            {heroItems.length === 0 ? (
                <p className="text-sm text-success">Nothing needs your attention right now — you&apos;re all caught up.</p>
            ) : (
                <div className="space-y-2">
                    {heroItems.map((item, i) => {
                        const act = actionFor(item);
                        return (
                            <div
                                key={i}
                                className={`flex items-start gap-3 p-3 rounded-lg bg-[#0f0f0f] border border-surface-hover border-l-2 ${CLASS_EDGE[item.cls]}`}
                            >
                                <span className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${CLASS_DOT[item.cls]}`} />
                                <div className="min-w-0 flex-1">
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${CLASS_CHIP[item.cls]}`}>
                                            {CLASS_LABEL[item.cls]}
                                        </span>
                                        <p className="text-sm text-text font-medium">{item.title}</p>
                                    </div>
                                    {item.detail && <p className="text-xs text-text-dim mt-1">{item.detail}</p>}
                                    <ExplainButton item={item} label={item.title} />
                                </div>
                                <Link
                                    href={act.href}
                                    className="flex-shrink-0 inline-flex items-center gap-1 text-xs text-[var(--accent)] hover:underline"
                                >
                                    {act.label} <ArrowRight className="w-3 h-3" />
                                </Link>
                            </div>
                        );
                    })}
                </div>
            )}
        </SectionCard>
    );
}
