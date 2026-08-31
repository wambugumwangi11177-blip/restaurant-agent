"use client";

/**
 * /dashboard/ai/[module] — the full, extensive dashboard for one AI module.
 * The Overview (/dashboard/ai) shows compact summaries; each module
 * links here for the complete payload. Registry-driven: add a module in
 * _full/registry.tsx and link it from the hub section via ModuleShell fullHref.
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Brain } from "lucide-react";
import { FULL_MODULES } from "../_full/registry";

export default function ModuleDashboardPage() {
    const params = useParams<{ module: string }>();
    const slug = params?.module;
    const mod = slug ? FULL_MODULES[slug] : undefined;

    if (!mod) {
        return (
            <div className="space-y-4">
                <Link href="/dashboard/ai" className="flex items-center gap-2 text-text-dim text-sm hover:text-text">
                    <ArrowLeft className="w-4 h-4" /> Back to Overview
                </Link>
                <div className="rounded-xl border border-surface-hover bg-[#0f0f0f] p-8 text-center">
                    <Brain className="w-8 h-8 text-[var(--accent)] mx-auto mb-3" />
                    <p className="text-text font-medium">No full dashboard for this module</p>
                    <p className="text-text-dim text-sm mt-1">It either lives entirely on the AI hub or on its own page.</p>
                </div>
            </div>
        );
    }

    const Full = mod.Component;
    return (
        <div className="space-y-5">
            <Link href="/dashboard/ai" className="flex items-center gap-2 text-text-dim text-sm hover:text-text w-fit">
                <ArrowLeft className="w-4 h-4" /> Overview
            </Link>
            <div>
                <h1 className="text-2xl font-bold text-text">{mod.title}</h1>
                <p className="text-text-dim mt-1 text-sm">{mod.subtitle}</p>
            </div>
            <Full />
        </div>
    );
}
