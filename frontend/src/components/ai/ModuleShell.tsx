"use client";

/**
 * frontend/src/components/ai/ModuleShell.tsx
 * Card wrapper for a self-contained AI/analytics module: title, optional
 * subtitle, an optional "How this works" explainer, and shared loading / error
 * / retry states so one module failing never takes the page down.
 */

import { HowItWorks } from "./HowItWorks";
import type { LucideIcon } from "lucide-react";
import { ArrowRight } from "lucide-react";
import Link from "next/link";

export function ModuleShell({
    icon: Icon, title, subtitle, explainKey, loading, error, onRetry, fullHref, children,
}: {
    icon: LucideIcon;
    title: string;
    subtitle?: string;
    explainKey?: string;
    loading: boolean;
    error: string;
    onRetry: () => void;
    /** Link to this module's extensive sub-dashboard (/dashboard/ai/[module]). */
    fullHref?: string;
    children: React.ReactNode;
}) {
    return (
        <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
            <div className="flex items-start justify-between gap-2">
                <h2 className="text-sm font-semibold text-[#e5e5e5] flex items-center gap-2">
                    <Icon className="w-4 h-4 text-[var(--accent)]" />
                    {title}
                </h2>
                {fullHref && (
                    <Link href={fullHref} className="flex items-center gap-1 text-xs text-[var(--accent)] hover:underline whitespace-nowrap">
                        Full dashboard <ArrowRight className="w-3 h-3" />
                    </Link>
                )}
            </div>
            {subtitle && <p className="text-xs text-[#525252] mt-1">{subtitle}</p>}
            {explainKey && <HowItWorks id={explainKey} />}
            <div className="mb-4" />
            {loading ? (
                <div className="space-y-2">
                    <div className="bg-[#141414] rounded-lg h-16 animate-pulse" />
                </div>
            ) : error ? (
                <div className="py-2">
                    <div className="flex items-center justify-between gap-3">
                        <p className="text-[#a3a3a3] text-sm">This module couldn&apos;t analyse your data just now.</p>
                        <button onClick={onRetry} className="text-xs text-[var(--accent)] hover:underline flex-shrink-0">Retry</button>
                    </div>
                    {/* Raw backend/network detail stays available for
                        debugging, tucked behind a toggle instead of being
                        the headline the user reads. */}
                    <details className="mt-1.5">
                        <summary className="text-[11px] text-[#525252] cursor-pointer hover:text-[#737373] select-none">Details</summary>
                        <p className="text-[11px] text-[#525252] mt-1 break-words">{error}</p>
                    </details>
                </div>
            ) : (
                children
            )}
        </div>
    );
}
