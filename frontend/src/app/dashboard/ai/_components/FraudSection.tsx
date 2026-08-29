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

    // "jane@mamas.co.ke" → "Jane" — a person, not an email address, is what
    // the owner needs to read at a glance during a shift.
    const friendlyActor = (email?: string) => {
        if (!email) return "Unknown staff member";
        const local = email.split("@")[0].split(/[._\-+\d]/)[0];
        if (!local) return email;
        return local.charAt(0).toUpperCase() + local.slice(1).toLowerCase();
    };

    return (
        <ModuleShell
            icon={ShieldCheck}
            title="Fraud Watch"
            subtitle={`We watch for unusual voids, rapid refunds, payment mismatches and after-hours changes over the last ${data?.window_hours ?? 24}h — so you don't have to.`}
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
                                <p className="text-red-300 font-medium">Unusual cancel/void activity</p>
                                <p className="text-text-dim text-xs mt-0.5">
                                    Involving {data.void_spikes.map(v => friendlyActor(v.actor_email)).join(", ")}
                                </p>
                            </div>
                        )}
                        {data.refund_velocity.length > 0 && (
                            <div className="p-3 rounded-lg bg-red-500/5 border border-red-500/20 text-sm">
                                <p className="text-red-300 font-medium">Rapid refunds</p>
                                <p className="text-text-dim text-xs mt-0.5">
                                    {data.refund_velocity.map(v => `${friendlyActor(v.actor_email)} (${v.count} refunds)`).join(", ")}
                                </p>
                            </div>
                        )}
                        {data.payment_mismatches.length > 0 && (
                            <div className="p-3 rounded-lg bg-amber-500/5 border border-amber-500/20 text-sm">
                                <p className="text-amber-300 font-medium">Payments that don&apos;t match orders</p>
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
