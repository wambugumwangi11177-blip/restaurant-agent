"use client";

/**
 * SectionCard — one shared card wrapper for dashboard panels, so stacked
 * cards keep an identical rhythm (padding, border, radius, header) instead
 * of each page hand-rolling slightly different geometry. Optional header
 * icon/title/subtitle and an optional right-aligned header action.
 */
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export default function SectionCard({
    icon: Icon,
    title,
    subtitle,
    action,
    children,
    className = "",
}: {
    icon?: LucideIcon;
    title?: string;
    subtitle?: string;
    action?: ReactNode;
    children: ReactNode;
    className?: string;
}) {
    return (
        <section className={`rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 ${className}`}>
            {(title || action) && (
                <div className="flex items-start justify-between gap-3 mb-4">
                    <div>
                        {title && (
                            <h2 className="text-sm font-semibold text-[var(--text)] flex items-center gap-2">
                                {Icon && <Icon className="w-4 h-4 text-[var(--accent)]" />}
                                {title}
                            </h2>
                        )}
                        {subtitle && <p className="text-xs text-[var(--text-dim)] mt-1">{subtitle}</p>}
                    </div>
                    {action && <div className="shrink-0">{action}</div>}
                </div>
            )}
            {children}
        </section>
    );
}
