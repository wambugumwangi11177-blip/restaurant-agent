"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import api from "@/lib/api";
import {
    Wallet, CheckCircle2, AlertTriangle, XCircle, Loader2, Clock,
} from "lucide-react";

interface Subscription {
    plan: string;
    status: string;          // effective status: trialing | active | past_due | canceled
    stored_status: string;
    provider: string;
    current_period_end: string | null;
    days_remaining: number | null;
    in_grace_period: boolean;
    is_active: boolean;
}

const PLANS = ["free", "pro", "enterprise"] as const;

export default function BillingPage() {
    const [sub, setSub] = useState<Subscription | null>(null);
    const [loading, setLoading] = useState(true);
    const [recording, setRecording] = useState(false);
    const [changingPlan, setChangingPlan] = useState(false);
    const [cancelling, setCancelling] = useState(false);
    const [days, setDays] = useState("30");
    const [error, setError] = useState("");

    const fetchSub = () => {
        api.get("/billing/").then((r) => setSub(r.data)).catch(() => { }).finally(() => setLoading(false));
    };

    useEffect(() => { fetchSub(); }, []);

    const handleRecordPayment = async () => {
        setError("");
        setRecording(true);
        try {
            const res = await api.post("/billing/record-payment", { days: parseInt(days) || 30 });
            setSub(res.data);
        } catch (err: any) {
            setError(err?.response?.data?.detail || "Couldn't record the payment.");
        }
        setRecording(false);
    };

    const handleChangePlan = async (plan: string) => {
        setChangingPlan(true);
        try {
            const res = await api.post("/billing/plan", { plan });
            setSub(res.data);
        } catch { }
        setChangingPlan(false);
    };

    const handleCancel = async () => {
        if (!confirm("Cancel this subscription? Intelligence features (AI, pricing, ROI, reports) will stop until you renew. POS, Kitchen and orders are never affected.")) return;
        setCancelling(true);
        try {
            const res = await api.post("/billing/cancel");
            setSub(res.data);
        } catch { }
        setCancelling(false);
    };

    if (loading) {
        return (
            <div className="space-y-4">
                <div className="bg-[#141414] rounded-xl h-32 animate-pulse" />
                <div className="bg-[#141414] rounded-xl h-40 animate-pulse" />
            </div>
        );
    }

    if (!sub) {
        return <p className="text-sm text-[#525252]">Couldn&apos;t load billing information.</p>;
    }

    const statusMeta: Record<string, { label: string; color: string; icon: any }> = {
        trialing: { label: "On trial", color: "#3b82f6", icon: Clock },
        active: { label: "Active", color: "#22c55e", icon: CheckCircle2 },
        past_due: { label: "Past due", color: "#ef4444", icon: AlertTriangle },
        canceled: { label: "Canceled", color: "#737373", icon: XCircle },
    };
    const meta = statusMeta[sub.status] || statusMeta.past_due;
    const StatusIcon = meta.icon;

    return (
        <div className="space-y-5 max-w-2xl">
            <div>
                <h1 className="text-xl font-bold text-[#e5e5e5]">Billing</h1>
                <p className="text-sm text-[#525252] mt-0.5">Your subscription and what it unlocks</p>
            </div>

            {/* Status card */}
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                className="bg-[#141414] border border-[#262626] rounded-xl p-5">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-full flex items-center justify-center" style={{ backgroundColor: `${meta.color}1a` }}>
                            <StatusIcon className="w-5 h-5" style={{ color: meta.color }} />
                        </div>
                        <div>
                            <p className="text-sm font-semibold text-[#e5e5e5] capitalize">{sub.plan} plan</p>
                            <p className="text-xs" style={{ color: meta.color }}>{meta.label}</p>
                        </div>
                    </div>
                    {sub.days_remaining !== null && (
                        <div className="text-right">
                            <p className="text-lg font-bold text-[#e5e5e5]">{sub.days_remaining}</p>
                            <p className="text-[10px] text-[#525252]">days left</p>
                        </div>
                    )}
                </div>

                {sub.in_grace_period && (
                    <div className="mt-3 flex items-center gap-2 text-[10px] text-[#eab308] bg-[#eab308]/10 border border-[#eab308]/20 rounded-lg px-3 py-2">
                        <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                        Your period ended but you&apos;re still within the grace window — renew soon to avoid losing access.
                    </div>
                )}
                {!sub.is_active && (
                    <div className="mt-3 flex items-center gap-2 text-[10px] text-[#ef4444] bg-[#ef4444]/10 border border-[#ef4444]/20 rounded-lg px-3 py-2">
                        <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                        AI insights, pricing recommendations, ROI and reports are paused. POS, Kitchen, Orders and Stock
                        are never affected by billing — you can always keep serving customers.
                    </div>
                )}

                {sub.current_period_end && (
                    <p className="text-[10px] text-[#525252] mt-3">
                        {sub.is_active ? "Renews" : "Expired"} {new Date(sub.current_period_end).toLocaleDateString("en-KE", { day: "numeric", month: "long", year: "numeric" })}
                    </p>
                )}
            </motion.div>

            {/* Record a payment */}
            <div className="bg-[#141414] border border-[#262626] rounded-xl p-5">
                <p className="text-xs font-semibold text-[#e5e5e5] mb-1">Record a payment</p>
                <p className="text-[10px] text-[#525252] mb-3">
                    Paid by M-Pesa till or bank transfer? Record it here to extend your access.
                </p>
                <div className="flex items-center gap-2">
                    <input type="number" value={days} onChange={(e) => setDays(e.target.value)}
                        className="w-24 bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] focus:border-[#d4a853]/50 focus:outline-none" />
                    <span className="text-xs text-[#525252]">days</span>
                    <button onClick={handleRecordPayment} disabled={recording}
                        className="ml-auto flex items-center gap-1.5 bg-[#d4a853] text-black rounded-lg px-4 py-2 text-xs font-semibold disabled:opacity-50 transition-colors">
                        {recording ? <Loader2 className="w-3 h-3 animate-spin" /> : <Wallet className="w-3 h-3" />}
                        Record payment
                    </button>
                </div>
                {error && <p className="text-[10px] text-[#ef4444] mt-2">{error}</p>}
            </div>

            {/* Plan tier */}
            <div className="bg-[#141414] border border-[#262626] rounded-xl p-5">
                <p className="text-xs font-semibold text-[#e5e5e5] mb-1">Plan</p>
                <p className="text-[10px] text-[#525252] mb-3">
                    Changing your plan doesn&apos;t extend your access — record a payment for that.
                </p>
                <div className="flex gap-2">
                    {PLANS.map((plan) => (
                        <button key={plan} onClick={() => handleChangePlan(plan)} disabled={changingPlan || sub.plan === plan}
                            className={`flex-1 px-3 py-2 rounded-lg text-xs font-medium capitalize transition-colors ${sub.plan === plan
                                    ? "bg-[#d4a853]/10 text-[#d4a853] border border-[#d4a853]/30"
                                    : "bg-[#1a1a1a] text-[#737373] border border-[#262626] hover:text-[#e5e5e5]"
                                }`}>
                            {plan}
                        </button>
                    ))}
                </div>
            </div>

            {/* Cancel */}
            {sub.status !== "canceled" && (
                <div className="flex justify-end">
                    <button onClick={handleCancel} disabled={cancelling}
                        className="text-xs text-[#737373] hover:text-[#ef4444] disabled:opacity-50 transition-colors">
                        {cancelling ? "Cancelling..." : "Cancel subscription"}
                    </button>
                </div>
            )}
        </div>
    );
}
