"use client";

/**
 * /dashboard/marketing — Growth: Campaigns & Win-back
 *
 * A read-only, owner-facing view of the restaurant's growth levers, backed by
 * GET /ai/marketing (backend/ai/marketing/insights.py):
 *   - AI-suggested offers, each with a plain-language WHY and a margin-safety flag
 *   - Win-back of lapsed regulars (who they are, the exact message, recoverable value)
 *   - The reachable, consent-gated audience and how consent/opt-out protects customers
 *   - Recent campaign history from the message log
 *   - A static offer playbook library
 *
 * The AI only SUGGESTS. Every send is explicit and confirmed by the owner, goes
 * through the existing consent-gated / opt-out-respecting WhatsApp path
 * (POST /ai/marketing/promo and /ai/marketing/winback), and never runs on its own.
 */

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { formatKES } from "@/lib/format";
import { HowItWorks } from "@/components/ai/HowItWorks";
import { NarrativeBlock, type Narrative } from "@/components/ai/NarrativeBlock";
import {
    Megaphone, RefreshCw, AlertTriangle, Users, ShieldCheck, Gift,
    Sparkles, Send, CheckCircle, Clock, BookOpen, TrendingUp,
} from "lucide-react";
import EmptyState from "@/components/ui/EmptyState";
import type { ConfirmTarget } from "./_components/CampaignForm";
import { getErrorMessage } from "@/lib/errors";

const ConfirmSend = dynamic(() => import("./_components/ConfirmSend"));
const CampaignForm = dynamic(() => import("./_components/CampaignForm"));

interface Offer {
    id: string;
    type: string;
    title: string;
    offer_text: string;
    audience_label: string;
    why: string;
    expected_impact_cents?: number | null;
    margin_safe: boolean;
    margin_note?: string;
    source: string;
    action: "winback" | "promo";
    reachable?: number;
}

interface WinbackCandidate {
    name: string;
    days_away: number;
    total_spend_cents: number;
    order_count: number;
    fav_item: string | null;
    message: string;
}

interface MarketingData {
    window_days: number;
    winback: {
        lapse_days: number;
        count: number;
        reachable: number;
        past_spend_cents: number;
        candidates: WinbackCandidate[];
    };
    audience: {
        promo_reachable: number;
        consented_customers: number;
        order_window_days: number;
        send_cap: number;
    };
    history: { type: string; label: string; sent: number; not_delivered: number; last_sent: string | null }[];
    suggested_offers: Offer[];
    narrative?: Narrative;
    error?: string;
}

// Static offer playbook — the "what offers exist and when to use them" library.
const PLAYBOOK = [
    {
        name: "Win-back discount",
        icon: Users,
        when: "A regular hasn't visited in 3+ weeks.",
        offer: "10% off your next visit, mentioning their favourite dish.",
        impact: "Cheapest possible sale — they already know and like you.",
        margin: "A one-off small discount keeps a healthy margin.",
    },
    {
        name: "Feature a hidden gem",
        icon: TrendingUp,
        when: "A dish has great margin but few order it (a 'Puzzle').",
        offer: "Chef's-pick shout-out or better menu placement — no discount.",
        impact: "Pure-profit orders; you're selling margin you already have.",
        margin: "No discount, so margin is untouched.",
    },
    {
        name: "Near-expiry flash",
        icon: Clock,
        when: "Stock is at spoilage risk and will otherwise be binned.",
        offer: "Today-only special on dishes using that ingredient.",
        impact: "Turns waste into revenue and recovers sunk cost.",
        margin: "Even discounted, it beats throwing stock away.",
    },
    {
        name: "Happy hour / slow-day boost",
        icon: Gift,
        when: "A daypart or weekday earns well below average.",
        offer: "Time-boxed deal (e.g. 15% off mains 3–6pm).",
        impact: "Fills empty seats when the kitchen has spare capacity.",
        margin: "Cap the discount and the time window to protect margin.",
    },
    {
        name: "Bundle / combo",
        icon: Gift,
        when: "You want to lift average spend per order.",
        offer: "Main + side + drink at a small saving vs buying separately.",
        impact: "Raises order value; the extra items carry their own margin.",
        margin: "Price the bundle above combined food cost + target margin.",
    },
];

export default function MarketingPage() {
    const { user } = useAuth();
    const [data, setData] = useState<MarketingData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
    const [confirm, setConfirm] = useState<ConfirmTarget | null>(null);
    const [banner, setBanner] = useState("");

    const restaurantName = user?.restaurant_name || "Your Restaurant";

    const fetchData = async () => {
        setLoading(true);
        setError("");
        try {
            const res = await api.get("/ai/marketing");
            setData(res.data);
            setLastUpdated(new Date());
        } catch (e) {
            setError(getErrorMessage(e, "Could not load marketing data"));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchData(); }, []);

    if (loading) {
        return (
            <div className="space-y-4">
                <div className="bg-surface rounded-xl h-8 w-56 animate-pulse" />
                <div className="bg-surface rounded-xl h-24 animate-pulse" />
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {[...Array(2)].map((_, i) => <div key={i} className="bg-surface rounded-xl h-40 animate-pulse" />)}
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[50vh] space-y-4">
                <AlertTriangle className="w-10 h-10 text-amber-400" />
                <p className="text-text font-medium">Could not load marketing data</p>
                <p className="text-text-dim text-sm text-center max-w-sm">{error}</p>
                <button onClick={fetchData} className="px-4 py-2 bg-[var(--accent)] text-bg font-semibold rounded-lg text-sm hover:bg-[var(--accent-hover)]">Retry</button>
            </div>
        );
    }

    const d = data!;
    const wb = d.winback;
    const isEmpty =
        wb.count === 0 &&
        d.suggested_offers.length === 0 &&
        d.history.length === 0 &&
        d.audience.promo_reachable === 0 &&
        d.audience.consented_customers === 0;
    if (isEmpty) {
        return (
            <EmptyState
                pageTitle="Growth — Campaigns & Win-back"
                pageSubtitle="Getting started"
                icon={Megaphone}
                title="No campaign audience yet"
                description="Once customers order and opt in at checkout, the AI will suggest offers to run, find lapsed regulars to win back, and show exactly who each campaign can reach — all consent-gated, and never sent without your approval."
            />
        );
    }

    return (
        <div className="space-y-6">
            <div className="flex items-start justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-text">Growth — Campaigns & Win-back</h1>
                    <p className="text-text-dim mt-1 text-sm">{restaurantName} — offers the AI suggests, ready for your approval</p>
                </div>
                <button onClick={fetchData} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-surface border border-border text-text-muted hover:text-text text-sm transition-colors">
                    <RefreshCw className="w-3.5 h-3.5" />
                    <span>{lastUpdated ? lastUpdated.toLocaleTimeString() : "Refresh"}</span>
                </button>
            </div>

            {/* Success banner after a send */}
            {banner && (
                <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3">
                    <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                    <p className="text-sm text-text">{banner}</p>
                </div>
            )}

            {/* How campaigns work */}
            <div className="rounded-xl border border-[var(--accent)]/25 bg-[var(--accent)]/[0.04] p-5">
                <div className="flex items-center gap-2 text-[var(--accent)] mb-1">
                    <Sparkles className="w-4 h-4" />
                    <p className="text-sm font-semibold text-text">Where these campaigns come from</p>
                </div>
                <p className="text-sm text-[#a3a3a3] leading-relaxed">
                    The AI reads your menu, your stock and your customers, then suggests specific offers worth
                    running — and tells you <span className="text-text font-medium">why</span> each one makes sense.
                    Nothing is sent automatically: you approve every campaign, and only customers who gave consent
                    at checkout and haven&apos;t opted out are ever contacted.
                </p>
                <HowItWorks id="marketing" />
            </div>

            {/* Grounded AI reading */}
            <NarrativeBlock n={d.narrative} />

            {/* Suggested offers */}
            <CampaignForm offers={d.suggested_offers} onPick={setConfirm} />

            {/* Win-back */}
            <div className="rounded-xl border border-surface-hover bg-[#0f0f0f] p-5">
                <div className="flex items-start justify-between gap-3">
                    <div>
                        <h2 className="text-sm font-semibold text-text flex items-center gap-2">
                            <Users className="w-4 h-4 text-[var(--accent)]" /> Win back your lapsed regulars
                        </h2>
                        <p className="text-xs text-text-dim mt-1">
                            Customers who used to visit but have gone quiet for {wb.lapse_days}+ days.
                        </p>
                    </div>
                    {wb.reachable > 0 && (
                        <button
                            onClick={() => setConfirm({
                                title: `Win back ${wb.reachable} lapsed regular${wb.reachable === 1 ? "" : "s"}`,
                                offer_text: "10% off your next visit (personalised with each customer's favourite dish)",
                                audience_label: `${wb.reachable} reachable now`,
                                action: "winback",
                            })}
                            className="flex-shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[var(--accent)] text-bg font-semibold text-sm hover:bg-[var(--accent-hover)] transition-colors"
                        >
                            <Send className="w-3.5 h-3.5" /> Send win-back
                        </button>
                    )}
                </div>

                <HowItWorks id="winback" />

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 my-4">
                    <div className="rounded-lg bg-surface border border-surface-hover p-3">
                        <p className="text-xs text-text-dim mb-1">Lapsed regulars</p>
                        <p className="text-sm font-bold text-text">{wb.count}</p>
                    </div>
                    <div className="rounded-lg bg-surface border border-surface-hover p-3">
                        <p className="text-xs text-text-dim mb-1">Reachable now</p>
                        <p className="text-sm font-bold text-emerald-400">{wb.reachable}</p>
                    </div>
                    <div className="rounded-lg bg-surface border border-surface-hover p-3">
                        <p className="text-xs text-text-dim mb-1">Their past spend</p>
                        <p className="text-sm font-bold text-text">{formatKES(wb.past_spend_cents)}</p>
                    </div>
                </div>

                {wb.count > wb.reachable && (
                    <p className="text-[11px] text-text-dim mb-3">
                        {wb.count - wb.reachable} of these haven&apos;t opted in to marketing, so they can&apos;t be contacted — they&apos;re shown for context only.
                    </p>
                )}

                {wb.candidates.length === 0 ? (
                    <p className="text-emerald-400 text-sm flex items-center gap-2"><CheckCircle className="w-4 h-4" /> No regulars have lapsed — nice retention.</p>
                ) : (
                    <div className="space-y-2">
                        {wb.candidates.map((c, i) => (
                            <div key={i} className="rounded-lg bg-surface border border-surface-hover p-3">
                                <div className="flex items-center justify-between gap-2 text-sm">
                                    <span className="text-text font-medium">{c.name}</span>
                                    <span className="text-text-dim text-xs whitespace-nowrap">{c.days_away} days away · {formatKES(c.total_spend_cents)} spent</span>
                                </div>
                                <p className="text-xs text-text-muted mt-1">
                                    {c.fav_item ? <>Favourite: <span className="text-[#a3a3a3]">{c.fav_item}</span> · </> : null}
                                    {c.order_count} past order{c.order_count === 1 ? "" : "s"}
                                </p>
                            </div>
                        ))}
                        {wb.candidates[0]?.message && (
                            <details className="mt-2">
                                <summary className="text-xs text-[var(--accent)] cursor-pointer hover:underline">Preview the message they&apos;ll receive</summary>
                                <pre className="mt-2 whitespace-pre-wrap text-[11px] text-[#a3a3a3] bg-bg border border-surface-hover rounded-lg p-3 font-sans">{wb.candidates[0].message}</pre>
                            </details>
                        )}
                    </div>
                )}
            </div>

            {/* Audience & consent */}
            <div className="rounded-xl border border-surface-hover bg-[#0f0f0f] p-5">
                <h2 className="text-sm font-semibold text-text flex items-center gap-2">
                    <ShieldCheck className="w-4 h-4 text-[var(--accent)]" /> Who you can reach — and how customers are protected
                </h2>
                <HowItWorks id="consent" />
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
                    <div className="rounded-lg bg-surface border border-surface-hover p-3">
                        <p className="text-xs text-text-dim mb-1">Promo reach now</p>
                        <p className="text-sm font-bold text-text">{d.audience.promo_reachable}</p>
                    </div>
                    <div className="rounded-lg bg-surface border border-surface-hover p-3">
                        <p className="text-xs text-text-dim mb-1">Consented customers</p>
                        <p className="text-sm font-bold text-text">{d.audience.consented_customers}</p>
                    </div>
                    <div className="rounded-lg bg-surface border border-surface-hover p-3">
                        <p className="text-xs text-text-dim mb-1">Order window</p>
                        <p className="text-sm font-bold text-text">{d.audience.order_window_days} days</p>
                    </div>
                    <div className="rounded-lg bg-surface border border-surface-hover p-3">
                        <p className="text-xs text-text-dim mb-1">Per-send cap</p>
                        <p className="text-sm font-bold text-text">{d.audience.send_cap}</p>
                    </div>
                </div>
            </div>

            {/* Campaign history */}
            {d.history.length > 0 && (
                <div className="rounded-xl border border-surface-hover bg-[#0f0f0f] p-5">
                    <h2 className="text-sm font-semibold text-text flex items-center gap-2 mb-4">
                        <Clock className="w-4 h-4 text-[var(--accent)]" /> What&apos;s gone out (last 90 days)
                    </h2>
                    <div className="space-y-2">
                        {d.history.map((h) => {
                            const total = h.sent + h.not_delivered;
                            const pct = total > 0 ? Math.round((h.sent / total) * 100) : 0;
                            return (
                                <div key={h.type} className="text-sm">
                                    <div className="flex items-center justify-between gap-2">
                                        <span className="text-[#a3a3a3]">{h.label}</span>
                                        <span className="text-text-dim text-xs whitespace-nowrap">{h.sent} delivered{h.not_delivered ? ` · ${h.not_delivered} not delivered` : ""}</span>
                                    </div>
                                    <div className="mt-1 h-1.5 bg-surface-hover rounded-full overflow-hidden">
                                        <div className="h-full bg-emerald-400 rounded-full" style={{ width: `${pct}%` }} />
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* Offer playbook library */}
            <div className="rounded-xl border border-surface-hover bg-[#0f0f0f] p-5">
                <h2 className="text-sm font-semibold text-text flex items-center gap-2 mb-1">
                    <BookOpen className="w-4 h-4 text-[var(--accent)]" /> Offer playbook
                </h2>
                <p className="text-xs text-text-dim mb-4">The main campaign types, when to use each, and how to keep the margin safe.</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {PLAYBOOK.map((p) => (
                        <div key={p.name} className="rounded-lg bg-surface border border-surface-hover p-4">
                            <div className="flex items-center gap-2 mb-2">
                                <p.icon className="w-4 h-4 text-[var(--accent)]" />
                                <p className="text-sm font-medium text-text">{p.name}</p>
                            </div>
                            <p className="text-[11px] text-text-muted"><span className="text-text-dim">When:</span> {p.when}</p>
                            <p className="text-[11px] text-text-muted mt-1"><span className="text-text-dim">Offer:</span> {p.offer}</p>
                            <p className="text-[11px] text-emerald-400/80 mt-1">📈 {p.impact}</p>
                            <p className="text-[11px] text-text-dim mt-1">🛡 {p.margin}</p>
                        </div>
                    ))}
                </div>
            </div>

            {confirm && (
                <ConfirmSend
                    offer={confirm}
                    onClose={() => setConfirm(null)}
                    onSent={(msg) => { setConfirm(null); setBanner(msg); }}
                />
            )}
        </div>
    );
}
