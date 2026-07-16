"use client";

/**
 * frontend/src/components/ai/ModuleShell.tsx
 * Card wrapper for a self-contained AI/analytics module: title, optional
 * subtitle, an optional "How this works" explainer, and shared loading / error
 * / retry states so one module failing never takes the page down.
 */

import { HowItWorks } from "./HowItWorks";

export function ModuleShell({
    icon: Icon, title, subtitle, explainKey, loading, error, onRetry, children,
}: {
    icon: any;
    title: string;
    subtitle?: string;
    explainKey?: string;
    loading: boolean;
    error: string;
    onRetry: () => void;
    children: React.ReactNode;
}) {
    return (
        <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
            <h2 className="text-sm font-semibold text-[#e5e5e5] flex items-center gap-2">
                <Icon className="w-4 h-4 text-[var(--accent)]" />
                {title}
            </h2>
            {subtitle && <p className="text-xs text-[#525252] mt-1">{subtitle}</p>}
            {explainKey && <HowItWorks id={explainKey} />}
            <div className="mb-4" />
            {loading ? (
                <div className="space-y-2">
                    <div className="bg-[#141414] rounded-lg h-16 animate-pulse" />
                </div>
            ) : error ? (
                <div className="flex items-center justify-between gap-3 py-2">
                    <p className="text-[#525252] text-sm">{error}</p>
                    <button onClick={onRetry} className="text-xs text-[var(--accent)] hover:underline flex-shrink-0">Retry</button>
                </div>
            ) : (
                children
            )}
        </div>
    );
}
