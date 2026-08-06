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
import api, { errorMessage } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { formatKES } from "@/lib/format";
import { HowItWorks } from "@/components/ai/HowItWorks";
import { NarrativeBlock, type Narrative } from "@/components/ai/NarrativeBlock";
import {
    Megaphone, RefreshCw, AlertTriangle, Users, ShieldCheck, Gift,
    Sparkles, Send, X, CheckCircle, Clock, BookOpen, TrendingUp,
} from "lucide-react";

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

function ConfirmSend({
    offer, onClose, onSent,
}: {
    offer: { title: string; offer_text: string; audience_label: string; action: "winback" | "promo" };
    onClose: () => void;
    onSent: (msg: string) => void;
}) {
    const [sending, setSending] = useState(false);
    const [error, setError] = useState("");

    const send = async () => {
        setSending(true);
        setError("");
        try {
            const res = offer.action === "winback"
                ? await api.post("/ai/marketing/winback")
                : await api.post("/ai/marketing/promo", { offer_text: offer.offer_text });
            if (res.data?.started) {
                onSent(res.data.message || "Your campaign is sending.");
            } else {
                setError(res.data?.error || "Nothing was sent.");
            }
        } catch (e: any) {
            setError(errorMessage(e, "Could not send the campaign."));
        } finally {
            setSending(false);
        }
    };

    return (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/60" onClick={onClose}>
            <div className="w-full max-w-md rounded-xl border border-[#262626] bg-[#0f0f0f] p-5 space-y-4" onClick={(e) => e.stopPropagation()}>
                <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2">
                        <Send className="w-4 h-4 text-[#d4a853]" />
                        <h3 className="text-sm font-semibold text-[#e5e5e5]">Send this campaign?</h3>
                    </div>
                    <button onClick={onClose} className="text-[#525252] hover:text-[#e5e5e5]"><X className="w-4 h-4" /></button>
                </div>

                <div className="rounded-lg border border-[#1a1a1a] bg-[#0a0a0a] p-3 space-y-1.5">
                    <p className="text-sm text-[#e5e5e5]">{offer.title}</p>
                    <p className="text-xs text-[#a3a3a3] italic">“{offer.offer_text}”</p>
                    <p className="text-[11px] text-[#737373]">Audience: {offer.audience_label}</p>
                </div>

                <p className="text-[11px] text-amber-400/90 flex gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                    <span>This sends real WhatsApp messages now. Only customers who gave consent and haven&apos;t opted out are contacted.</span>
                </p>

                {error && <p className="text-xs text-red-400">{error}</p>}

                <div className="flex items-center justify-end gap-2">
                    <button onClick={onClose} className="px-3 py-2 rounded-lg text-sm text-[#737373] hover:text-[#e5e5e5]">Cancel</button>
                    <button
                        onClick={send}
                        disabled={sending}
                        className="px-4 py-2 rounded-lg bg-[#d4a853] text-[#0a0a0a] font-semibold text-sm hover:bg-[#e0b96a] disabled:opacity-60"
                    >
                        {sending ? "Sending…" : "Yes, send it"}
                    </button>
                </div>
            </div>
        </div>
    );
}

function EmptyState() {
    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-[#e5e5e5]">Growth — Campaigns & Win-back</h1>
                <p className="text-[#525252] mt-1 text-sm">Getting started</p>
            </div>
            <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-8 text-center space-y-4">
                <Megaphone className="w-12 h-12 text-[#d4a853] mx-auto" />
                <h2 className="text-[#e5e5e5] font-semibold text-lg">No campaign audience yet</h2>
                <p className="text-[#525252] text-sm max-w-md mx-auto">
                    Once customers order and opt in at checkout, the AI will suggest offers to run,
                    find lapsed regulars to win back, and show exactly who each campaign can reach —
                    all consent-gated, and never sent without your approval.
                </p>
            </div>
        </div>
    );
}

export default function MarketingPage() {
    const { user } = useAuth();
    const [data, setData] = useState<MarketingData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
    const [confirm, setConfirm] = useState<{ title: string; offer_text: string; audience_label: string; action: "winback" | "promo" } | null>(null);
    const [banner, setBanner] = useState("");

    const restaurantName = (user as any)?.restaurant_name || "Your Restaurant";

    const fetchData = async () => {
        setLoading(true);
        setError("");
        try {
            const res = await api.get("/ai/marketing");
            setData(res.data);
            setLastUpdated(new Date());
        } catch (e: any) {
            setError(errorMessage(e, "Could not load marketing data"));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchData(); }, []);

    if (loading) {
        return (
            <div className="space-y-4">
                <div className="bg-[#141414] rounded-xl h-8 w-56 animate-pulse" />
                <div className="bg-[#141414] rounded-xl h-24 animate-pulse" />
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {[...Array(2)].map((_, i) => <div key={i} className="bg-[#141414] rounded-xl h-40 animate-pulse" />)}
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[50vh] space-y-4">
                <AlertTriangle className="w-10 h-10 text-amber-400" />
                <p className="text-[#e5e5e5] font-medium">Could not load marketing data</p>
                <p className="text-[#525252] text-sm text-center max-w-sm">{error}</p>
                <button onClick={fetchData} className="px-4 py-2 bg-[#d4a853] text-[#0a0a0a] font-semibold rounded-lg text-sm hover:bg-[#e0b96a]">Retry</button>
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
    if (isEmpty) return <EmptyState />;

    return (
        <div className="space-y-6">
            <div className="flex items-start justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-[#e5e5e5]">Growth — Campaigns & Win-back</h1>
                    <p className="text-[#525252] mt-1 text-sm">{restaurantName} — offers the AI suggests, ready for your approval</p>
                </div>
                <button onClick={fetchData} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#141414] border border-[#262626] text-[#737373] hover:text-[#e5e5e5] text-sm transition-colors">
                    <RefreshCw className="w-3.5 h-3.5" />
                    <span>{lastUpdated ? lastUpdated.toLocaleTimeString() : "Refresh"}</span>
                </button>
            </div>

            {/* Success banner after a send */}
            {banner && (
                <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3">
                    <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                    <p className="text-sm text-[#e5e5e5]">{banner}</p>
                </div>
            )}

            {/* How campaigns work */}
            <div className="rounded-xl border border-[#d4a853]/25 bg-[#d4a853]/[0.04] p-5">
                <div className="flex items-center gap-2 text-[#d4a853] mb-1">
                    <Sparkles className="w-4 h-4" />
                    <p className="text-sm font-semibold text-[#e5e5e5]">Where these campaigns come from</p>
                </div>
                <p className="text-sm text-[#a3a3a3] leading-relaxed">
                    The AI reads your menu, your stock and your customers, then suggests specific offers worth
                    running — and tells you <span className="text-[#e5e5e5] font-medium">why</span> each one makes sense.
                    Nothing is sent automatically: you approve every campaign, and only customers who gave consent
                    at checkout and haven&apos;t opted out are ever contacted.
                </p>
                <HowItWorks id="marketing" />
            </div>

            {/* Grounded AI reading */}
            <NarrativeBlock n={d.narrative} />

            {/* Suggested offers */}
            <div>
                <h2 className="text-sm font-semibold text-[#e5e5e5] mb-1 flex items-center gap-2">
                    <Gift className="w-4 h-4 text-[#d4a853]" /> Offers worth running now
                </h2>
                <p className="text-xs text-[#525252] mb-3">Each offer shows the exact deal, who it reaches, and why it&apos;s worth it.</p>
                {d.suggested_offers.length === 0 ? (
                    <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5 text-sm text-[#525252]">
                        No offers to suggest right now — add cost prices and let a few more orders come in, and suggestions will appear here.
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {d.suggested_offers.map((o) => (
                            <div key={o.id} className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5 flex flex-col">
                                <div className="flex items-start justify-between gap-2">
                                    <p className="text-sm font-semibold text-[#e5e5e5]">{o.title}</p>
                                    {o.margin_safe && (
                                        <span title={o.margin_note || "Margin stays healthy"} className="flex items-center gap-1 text-[10px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded px-1.5 py-0.5 whitespace-nowrap">
                                            <ShieldCheck className="w-3 h-3" /> Margin-safe
                                        </span>
                                    )}
                                </div>
                                <p className="text-xs text-[#a3a3a3] italic mt-2">“{o.offer_text}”</p>
                                <div className="mt-2 flex items-center gap-1.5 text-[11px] text-[#737373]">
                                    <Users className="w-3 h-3" /> {o.audience_label}
                                </div>
                                <p className="text-xs text-[#525252] mt-2 leading-relaxed flex-1">
                                    <span className="text-[#737373] font-medium">Why: </span>{o.why}
                                </p>
                                {o.margin_note && <p className="text-[11px] text-[#525252] mt-2">💡 {o.margin_note}</p>}
                                <button
                                    onClick={() => setConfirm({ title: o.title, offer_text: o.offer_text, audience_label: o.audience_label, action: o.action })}
                                    className="mt-4 self-start flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[#d4a853] text-[#0a0a0a] font-semibold text-sm hover:bg-[#e0b96a] transition-colors"
                                >
                                    <Send className="w-3.5 h-3.5" /> Send this
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Win-back */}
            <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
                <div className="flex items-start justify-between gap-3">
                    <div>
                        <h2 className="text-sm font-semibold text-[#e5e5e5] flex items-center gap-2">
                            <Users className="w-4 h-4 text-[#d4a853]" /> Win back your lapsed regulars
                        </h2>
                        <p className="text-xs text-[#525252] mt-1">
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
                            className="flex-shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[#d4a853] text-[#0a0a0a] font-semibold text-sm hover:bg-[#e0b96a] transition-colors"
                        >
                            <Send className="w-3.5 h-3.5" /> Send win-back
                        </button>
                    )}
                </div>

                <HowItWorks id="winback" />

                <div className="grid grid-cols-3 gap-3 my-4">
                    <div className="rounded-lg bg-[#141414] border border-[#1a1a1a] p-3">
                        <p className="text-xs text-[#525252] mb-1">Lapsed regulars</p>
                        <p className="text-sm font-bold text-[#e5e5e5]">{wb.count}</p>
                    </div>
                    <div className="rounded-lg bg-[#141414] border border-[#1a1a1a] p-3">
                        <p className="text-xs text-[#525252] mb-1">Reachable now</p>
                        <p className="text-sm font-bold text-emerald-400">{wb.reachable}</p>
                    </div>
                    <div className="rounded-lg bg-[#141414] border border-[#1a1a1a] p-3">
                        <p className="text-xs text-[#525252] mb-1">Their past spend</p>
                        <p className="text-sm font-bold text-[#e5e5e5]">{formatKES(wb.past_spend_cents)}</p>
                    </div>
                </div>

                {wb.count > wb.reachable && (
                    <p className="text-[11px] text-[#525252] mb-3">
                        {wb.count - wb.reachable} of these haven&apos;t opted in to marketing, so they can&apos;t be contacted — they&apos;re shown for context only.
                    </p>
                )}

                {wb.candidates.length === 0 ? (
                    <p className="text-emerald-400 text-sm flex items-center gap-2"><CheckCircle className="w-4 h-4" /> No regulars have lapsed — nice retention.</p>
                ) : (
                    <div className="space-y-2">
                        {wb.candidates.map((c, i) => (
                            <div key={i} className="rounded-lg bg-[#141414] border border-[#1a1a1a] p-3">
                                <div className="flex items-center justify-between gap-2 text-sm">
                                    <span className="text-[#e5e5e5] font-medium">{c.name}</span>
                                    <span className="text-[#525252] text-xs whitespace-nowrap">{c.days_away} days away · {formatKES(c.total_spend_cents)} spent</span>
                                </div>
                                <p className="text-xs text-[#737373] mt-1">
                                    {c.fav_item ? <>Favourite: <span className="text-[#a3a3a3]">{c.fav_item}</span> · </> : null}
                                    {c.order_count} past order{c.order_count === 1 ? "" : "s"}
                                </p>
                            </div>
                        ))}
                        {wb.candidates[0]?.message && (
                            <details className="mt-2">
                                <summary className="text-xs text-[#d4a853] cursor-pointer hover:underline">Preview the message they&apos;ll receive</summary>
                                <pre className="mt-2 whitespace-pre-wrap text-[11px] text-[#a3a3a3] bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg p-3 font-sans">{wb.candidates[0].message}</pre>
                            </details>
                        )}
                    </div>
                )}
            </div>

            {/* Audience & consent */}
            <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
                <h2 className="text-sm font-semibold text-[#e5e5e5] flex items-center gap-2">
                    <ShieldCheck className="w-4 h-4 text-[#d4a853]" /> Who you can reach — and how customers are protected
                </h2>
                <HowItWorks id="consent" />
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
                    <div className="rounded-lg bg-[#141414] border border-[#1a1a1a] p-3">
                        <p className="text-xs text-[#525252] mb-1">Promo reach now</p>
                        <p className="text-sm font-bold text-[#e5e5e5]">{d.audience.promo_reachable}</p>
                    </div>
                    <div className="rounded-lg bg-[#141414] border border-[#1a1a1a] p-3">
                        <p className="text-xs text-[#525252] mb-1">Consented customers</p>
                        <p className="text-sm font-bold text-[#e5e5e5]">{d.audience.consented_customers}</p>
                    </div>
                    <div className="rounded-lg bg-[#141414] border border-[#1a1a1a] p-3">
                        <p className="text-xs text-[#525252] mb-1">Order window</p>
                        <p className="text-sm font-bold text-[#e5e5e5]">{d.audience.order_window_days} days</p>
                    </div>
                    <div className="rounded-lg bg-[#141414] border border-[#1a1a1a] p-3">
                        <p className="text-xs text-[#525252] mb-1">Per-send cap</p>
                        <p className="text-sm font-bold text-[#e5e5e5]">{d.audience.send_cap}</p>
                    </div>
                </div>
            </div>

            {/* Campaign history */}
            {d.history.length > 0 && (
                <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
                    <h2 className="text-sm font-semibold text-[#e5e5e5] flex items-center gap-2 mb-4">
                        <Clock className="w-4 h-4 text-[#d4a853]" /> What&apos;s gone out (last 90 days)
                    </h2>
                    <div className="space-y-2">
                        {d.history.map((h) => {
                            const total = h.sent + h.not_delivered;
                            const pct = total > 0 ? Math.round((h.sent / total) * 100) : 0;
                            return (
                                <div key={h.type} className="text-sm">
                                    <div className="flex items-center justify-between gap-2">
                                        <span className="text-[#a3a3a3]">{h.label}</span>
                                        <span className="text-[#525252] text-xs whitespace-nowrap">{h.sent} delivered{h.not_delivered ? ` · ${h.not_delivered} not delivered` : ""}</span>
                                    </div>
                                    <div className="mt-1 h-1.5 bg-[#1a1a1a] rounded-full overflow-hidden">
                                        <div className="h-full bg-emerald-400 rounded-full" style={{ width: `${pct}%` }} />
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* Offer playbook library */}
            <div className="rounded-xl border border-[#1a1a1a] bg-[#0f0f0f] p-5">
                <h2 className="text-sm font-semibold text-[#e5e5e5] flex items-center gap-2 mb-1">
                    <BookOpen className="w-4 h-4 text-[#d4a853]" /> Offer playbook
                </h2>
                <p className="text-xs text-[#525252] mb-4">The main campaign types, when to use each, and how to keep the margin safe.</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {PLAYBOOK.map((p) => (
                        <div key={p.name} className="rounded-lg bg-[#141414] border border-[#1a1a1a] p-4">
                            <div className="flex items-center gap-2 mb-2">
                                <p.icon className="w-4 h-4 text-[#d4a853]" />
                                <p className="text-sm font-medium text-[#e5e5e5]">{p.name}</p>
                            </div>
                            <p className="text-[11px] text-[#737373]"><span className="text-[#525252]">When:</span> {p.when}</p>
                            <p className="text-[11px] text-[#737373] mt-1"><span className="text-[#525252]">Offer:</span> {p.offer}</p>
                            <p className="text-[11px] text-emerald-400/80 mt-1">📈 {p.impact}</p>
                            <p className="text-[11px] text-[#525252] mt-1">🛡 {p.margin}</p>
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
