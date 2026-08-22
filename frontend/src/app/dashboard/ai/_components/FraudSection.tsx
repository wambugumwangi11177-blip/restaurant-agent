"use client";

import { ShieldCheck } from "lucide-react";
import { useAiModule } from "@/lib/useAiModule";
import { ModuleShell } from "@/components/ai/ModuleShell";

interface FraudData {
    flagged: boolean;
    window_hours: number;
    void_spikes: { actor_email?: string }[];
    refund_velocity: { actor_email?: string; count?: number }[];
    payment_mismatches: { reason?: string }[];
    off_hours: unknown[];
}

export default function FraudSection() {
    const { data, loading, error, retry } = useAiModule<FraudData>("/fraud/report");

    return (
        <ModuleShell
            icon={ShieldCheck}
            title="Fraud Watch"
            subtitle={`Suspicious-transaction scan — void/cancel bursts, refund velocity, payment mismatches, off-hours activity (last ${data?.window_hours ?? 24}h).`}
            loading={loading}
            error={error}
            onRetry={retry}
            fullHref="/dashboard/ai/fraud"
        >
            {data && (
                data.flagged ? (
                    <div className="space-y-2">
                        {data.void_spikes.length > 0 && (
                            <div className="p-3 rounded-lg bg-red-500/5 border border-red-500/20 text-sm">
                                <p className="text-red-300 font-medium">Void/cancel spike</p>
                                <p className="text-text-dim text-xs mt-0.5">
                                    {data.void_spikes.map(v => v.actor_email).filter(Boolean).join(", ")}
                                </p>
                            </div>
                        )}
                        {data.refund_velocity.length > 0 && (
                            <div className="p-3 rounded-lg bg-red-500/5 border border-red-500/20 text-sm">
                                <p className="text-red-300 font-medium">Refund velocity</p>
                                <p className="text-text-dim text-xs mt-0.5">
                                    {data.refund_velocity.map(v => `${v.actor_email} (${v.count})`).join(", ")}
                                </p>
                            </div>
                        )}
                        {data.payment_mismatches.length > 0 && (
                            <div className="p-3 rounded-lg bg-amber-500/5 border border-amber-500/20 text-sm">
                                <p className="text-amber-300 font-medium">Payment mismatches</p>
                                <p className="text-text-dim text-xs mt-0.5">
                                    {data.payment_mismatches.map(v => v.reason).filter(Boolean).join("; ")}
                                </p>
                            </div>
                        )}
                    </div>
                ) : (
                    <p className="text-emerald-400 text-sm flex items-center gap-2">
                        No suspicious patterns in the last {data.window_hours}h — voids, refunds and payment records all look normal.
                    </p>
                )
            )}
        </ModuleShell>
    );
}
