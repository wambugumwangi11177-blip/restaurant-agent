"use client";

/** Shared primitives for the per-module full dashboards (/dashboard/ai/[module]). */

import { formatKESCompact } from "@/lib/format";

export function StatGrid({ stats }: { stats: { label: string; value: string; tone?: "ok" | "warn" | "bad" }[] }) {
    return (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
            {stats.map(s => (
                <div key={s.label} className="rounded-xl border border-surface-hover bg-[#0f0f0f] p-4">
                    <p className="text-xs text-text-dim mb-1">{s.label}</p>
                    <p className={`text-lg font-bold ${
                        s.tone === "bad" ? "text-red-400" : s.tone === "warn" ? "text-amber-400" : s.tone === "ok" ? "text-emerald-400" : "text-text"
                    }`}>{s.value}</p>
                </div>
            ))}
        </div>
    );
}

export function money(cents: number | null | undefined): string {
    return formatKESCompact(cents ?? 0);
}

export function DataTable({ columns, rows, empty = "No data" }: {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- render fns index arbitrary payload keys
    columns: { key: string; label: string; render?: (row: Record<string, any>) => React.ReactNode }[];
    rows: Record<string, any>[];
    empty?: string;
}) {
    if (!rows?.length) return <p className="text-text-dim text-sm py-2">{empty}</p>;
    return (
        <div className="overflow-x-auto rounded-xl border border-surface-hover">
            <table className="w-full text-sm">
                <thead>
                    <tr className="bg-surface text-left">
                        {columns.map(c => (
                            <th key={c.key} className="px-3 py-2 text-xs font-semibold text-text-dim whitespace-nowrap">{c.label}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((row, i) => (
                        <tr key={i} className="border-t border-surface-hover">
                            {columns.map(c => (
                                <td key={c.key} className="px-3 py-2 text-text whitespace-nowrap">
                                    {c.render ? c.render(row) : String(row[c.key] ?? "—")}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

export function SectionTitle({ children }: { children: React.ReactNode }) {
    return <h2 className="text-sm font-semibold text-text mb-2 mt-6 first:mt-0">{children}</h2>;
}

export function LoadingBlock() {
    return <div className="space-y-3"><div className="bg-surface rounded-xl h-20 animate-pulse" /><div className="bg-surface rounded-xl h-40 animate-pulse" /></div>;
}
