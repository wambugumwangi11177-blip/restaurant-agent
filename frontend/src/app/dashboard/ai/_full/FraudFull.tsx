"use client";

import { useAiModule } from "@/lib/useAiModule";
import { StatGrid, DataTable, SectionTitle, money, LoadingBlock } from "./shared";

interface FraudData {
    window_hours: number;
    flagged: boolean;
    void_spikes: Record<string, unknown>[];
    refund_velocity: Record<string, unknown>[];
    payment_mismatches: Record<string, unknown>[];
    off_hours: Record<string, unknown>[];
}

function PatternTable({ title, rows, cols }: { title: string; rows: Record<string, unknown>[]; cols: string[] }) {
    return (
        <>
            <SectionTitle>{title} ({rows.length})</SectionTitle>
            <DataTable
                columns={cols.map(k => ({ key: k, label: k.replace(/_/g, " ") }))}
                rows={rows }
                empty={`No ${title.toLowerCase()} detected.`} />
        </>
    );
}

export default function FraudFull() {
    const { data, loading, error, retry } = useAiModule<FraudData>("/fraud/report");
    if (loading) return <LoadingBlock />;
    if (error) return <div className="flex items-center gap-3"><p className="text-text-dim text-sm">{error}</p><button onClick={retry} className="px-3 py-1.5 rounded-lg bg-[var(--accent)] text-bg text-sm font-semibold">Retry</button></div>;
    if (!data) return null;
    const cols = (rows: Record<string, unknown>[]) => Object.keys(rows[0] ?? { detail: "" });
    return (
        <div>
            <StatGrid stats={[
                { label: "Status", value: data.flagged ? "Patterns flagged" : "Clean", tone: data.flagged ? "bad" : "ok" },
                { label: "Window", value: `Last ${data.window_hours}h` },
                { label: "Voids/Refunds", value: `${data.void_spikes.length} / ${data.refund_velocity.length}`, tone: (data.void_spikes.length + data.refund_velocity.length) > 0 ? "warn" : "ok" },
                { label: "Mismatches / Off-hours", value: `${data.payment_mismatches.length} / ${data.off_hours.length}`, tone: (data.payment_mismatches.length + data.off_hours.length) > 0 ? "warn" : "ok" },
            ]} />
            {!data.flagged && (
                <p className="text-emerald-400 text-sm mb-2">
                    No suspicious patterns in the last {data.window_hours} hours. Voids, refunds and payment records all look normal.
                </p>
            )}
            <PatternTable title="Void / cancel spikes" rows={data.void_spikes} cols={cols(data.void_spikes)} />
            <PatternTable title="Refund velocity" rows={data.refund_velocity} cols={cols(data.refund_velocity)} />
            <PatternTable title="Payment mismatches" rows={data.payment_mismatches} cols={cols(data.payment_mismatches)} />
            <PatternTable title="Off-hours activity" rows={data.off_hours} cols={cols(data.off_hours)} />
            <p className="text-text-dim text-xs mt-6">
                Detection reads the order audit trail — every void/refund/payment change with its actor and timestamp.
            </p>
        </div>
    );
}
