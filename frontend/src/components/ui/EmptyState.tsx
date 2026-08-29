"use client";

import { ReactNode } from "react";
import { LucideIcon } from "lucide-react";

interface EmptyStateProps {
    pageTitle: string;
    pageSubtitle: string;
    icon: LucideIcon;
    title: string;
    description: string;
    actions?: ReactNode;
}

export default function EmptyState({ pageTitle, pageSubtitle, icon: Icon, title, description, actions }: EmptyStateProps) {
    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-[var(--text)]">{pageTitle}</h1>
                <p className="text-[var(--text-dim)] mt-1 text-sm">{pageSubtitle}</p>
            </div>
            <div className="rounded-xl border border-[var(--surface-hover)] bg-[#0f0f0f] p-8 text-center space-y-4">
                <Icon className="w-12 h-12 text-[var(--accent)] mx-auto" />
                <h2 className="text-[var(--text)] font-semibold text-lg">{title}</h2>
                <p className="text-[var(--text-dim)] text-sm max-w-md mx-auto">{description}</p>
                {actions && <div className="flex flex-wrap gap-3 justify-center pt-2">{actions}</div>}
            </div>
        </div>
    );
}
