"use client";

import { useCallback, useEffect, useState } from "react";
import { Banknote } from "lucide-react";
import api from "@/lib/api";
import { formatKES } from "@/lib/format";
import { ModuleShell } from "@/components/ai/ModuleShell";

interface CashReport {
    flagged: boolean;
    drawer_variances: { count_id: number; expected_amount_cents: number; counted_amount_cents: number; variance_cents: number; flagged: boolean }[];
    mpesa_mismatches: { order_id: number; reason: string; total_cents: number }[];
}

export default function CashSection() {
    const [report, setReport] = useState<CashReport | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [countedKes, setCountedKes] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [message, setMessage] = useState("");

    const fetchReport = useCallback(() => {
        setLoading(true);
        api.get("/cash-reconciliation/report", { params: { hours: 24 } })
            .then(res => setReport(res.data))
            .catch(() => setError("Could not load reconciliation report"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { fetchReport(); }, [fetchReport]);

    const submit = async () => {
        const kes = Number(countedKes);
        if (!kes || kes < 0) { setMessage("Enter the amount counted in the drawer (KES)."); return; }
        setSubmitting(true);
        setMessage("");
        try {
            const now = new Date();
            const start = new Date(now.getTime() - 24 * 3600 * 1000);
            await api.post("/cash-reconciliation/counts", {
                counted_amount_cents: Math.round(kes * 100),
                window_start: start.toISOString(),
                window_end: now.toISOString(),
            });
            setMessage("Count recorded. Report updated below.");
            setCountedKes("");
            fetchReport();
        } catch (e: unknown) {
            const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
            setMessage(detail || "Could not record the count.");
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <ModuleShell
            icon={Banknote}
            title="Cash Drawer Reconciliation"
            subtitle="Count the drawer at shift end — the system compares it against what orders say should be there."
            loading={loading}
            error={error}
            onRetry={fetchReport}
        >
            <div className="flex flex-col sm:flex-row gap-2 mb-4">
                <input
                    aria-label="Counted amount (KES)"
                    inputMode="decimal"
                    placeholder="Counted in drawer (KES)"
                    className="flex-1 bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text"
                    value={countedKes}
                    onChange={e => setCountedKes(e.target.value)}
                />
                <button
                    onClick={submit}
                    disabled={submitting}
                    className="px-4 py-2 rounded-lg bg-[var(--accent)] text-bg font-semibold text-sm hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50"
                >
                    {submitting ? "Recording…" : "Record count (last 24h)"}
                </button>
            </div>
            {message && <p className="text-xs text-text-dim mb-3">{message}</p>}
            {report && (
                report.drawer_variances.length === 0 ? (
                    <p className="text-text-dim text-sm">No drawer counts in the last 24h — record one above to start reconciling.</p>
                ) : (
                    <div className="space-y-1.5">
                        {report.drawer_variances.slice(0, 4).map(v => (
                            <div key={v.count_id} className="flex items-center justify-between gap-3 p-2.5 rounded-lg bg-surface border border-surface-hover text-sm">
                                <span className="text-text-dim">Expected {formatKES(v.expected_amount_cents)}</span>
                                <span className="text-text">Counted {formatKES(v.counted_amount_cents)}</span>
                                <span className={v.flagged ? "text-red-400 font-medium" : "text-emerald-400"}>
                                    {v.variance_cents >= 0 ? "+" : ""}{formatKES(Math.abs(v.variance_cents))}
                                </span>
                            </div>
                        ))}
                    </div>
                )
            )}
        </ModuleShell>
    );
}
