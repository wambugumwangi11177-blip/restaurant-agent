"use client";

/**
 * AiTabs — the AI Command Center's module grouper. The hub previously
 * stacked ~20 section cards on one screen (overstimulating); modules now
 * live in four themed tabs so the default view is a calm summary.
 *
 * Keyboard: tabs are real buttons with role="tab"; ArrowLeft/ArrowRight move
 * between them (WAI-ARIA tabs pattern). The active tab is synced to the URL
 * hash (#money, #ops, #growth, #trust) so refresh/back keeps the tab.
 */
import { KeyboardEvent } from "react";

export const AI_TABS = [
    { id: "overview", label: "Summary" },
    { id: "money", label: "Money" },
    { id: "ops", label: "Operations" },
    { id: "growth", label: "Growth & Strategy" },
    { id: "trust", label: "Trust & Safety" },
] as const;

export type AiTabId = (typeof AI_TABS)[number]["id"];

export function tabFromHash(hash: string): AiTabId {
    const id = hash.replace("#", "");
    return (AI_TABS as readonly { id: string; label: string }[]).some((t) => t.id === id)
        ? (id as AiTabId)
        : "overview";
}

export default function AiTabs({
    active,
    onChange,
}: {
    active: AiTabId;
    onChange: (id: AiTabId) => void;
}) {
    function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        e.preventDefault();
        const idx = AI_TABS.findIndex((t) => t.id === active);
        const dir = e.key === "ArrowRight" ? 1 : -1;
        const next = AI_TABS[(idx + dir + AI_TABS.length) % AI_TABS.length];
        onChange(next.id);
        document.getElementById(`ai-tab-${next.id}`)?.focus();
    }

    return (
        <div
            role="tablist"
            aria-label="AI modules"
            onKeyDown={handleKeyDown}
            className="flex items-center gap-1 border-b border-[var(--border)] overflow-x-auto"
        >
            {AI_TABS.map((tab) => {
                const isActive = tab.id === active;
                return (
                    <button
                        key={tab.id}
                        id={`ai-tab-${tab.id}`}
                        role="tab"
                        aria-selected={isActive}
                        aria-controls={`ai-panel-${tab.id}`}
                        tabIndex={isActive ? 0 : -1}
                        onClick={() => onChange(tab.id)}
                        className={`px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 -mb-px transition-colors ${
                            isActive
                                ? "border-[var(--accent)] text-[var(--accent)]"
                                : "border-transparent text-[var(--text-muted)] hover:text-[var(--text)]"
                        }`}
                    >
                        {tab.label}
                    </button>
                );
            })}
        </div>
    );
}
