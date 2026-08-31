"use client";

/**
 * frontend/src/components/ai/InsightCard.tsx
 * The signature explanation shape for every intelligent insight:
 *   WHAT → WHY → IMPACT → ACTION → ACT
 * Instead of "AI recommends promoting high-margin items", the owner sees what
 * happened, why, what it costs them, and a button that does the next step.
 */
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { ExplainButton } from "@/components/ai/ExplainButton";
import { CLASS_CHIP, CLASS_LABEL, type AlertClass } from "@/app/dashboard/ai/_components/overview/taxonomy";

interface InsightCardProps {
    what: string;
    why?: string;
    impact?: string;
    actionLabel?: string;
    actionHref?: string;
    cls?: AlertClass;
    /** When provided, renders an "Explain this to me" grounded explainer. */
    explainItem?: object;
    explainLabel?: string;
}

export function InsightCard({
    what,
    why,
    impact,
    actionLabel,
    actionHref,
    cls = "information",
    explainItem,
    explainLabel,
}: InsightCardProps) {
    return (
        <div className="p-3 rounded-lg bg-[#0f0f0f] border border-surface-hover text-sm">
            <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 flex-wrap">
                    <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${CLASS_CHIP[cls]}`}>
                        {CLASS_LABEL[cls]}
                    </span>
                    <p className="text-text font-medium">{what}</p>
                </div>
            </div>

            {why && <p className="text-xs text-text-dim mt-1.5">{why}</p>}
            {impact && <p className="text-xs text-[var(--accent)] mt-1">{impact}</p>}

            {explainItem && <ExplainButton item={explainItem} label={explainLabel} />}

            {actionLabel && actionHref && (
                <Link
                    href={actionHref}
                    className="inline-flex items-center gap-1 mt-2 text-xs text-[var(--accent)] hover:underline"
                >
                    {actionLabel} <ArrowRight className="w-3 h-3" />
                </Link>
            )}
        </div>
    );
}
