"use client";

import { Gift, ShieldCheck, Users, Send } from "lucide-react";

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

export type ConfirmTarget = { title: string; offer_text: string; audience_label: string; action: "winback" | "promo" };

// The "offers worth running now" picker — reads the AI's suggested campaigns
// and lets the owner kick off the send-confirmation flow (ConfirmSend) for
// any one of them. Nothing here sends a message directly; onPick just opens
// the confirmation dialog in the parent.
export default function CampaignForm({ offers, onPick }: { offers: Offer[]; onPick: (target: ConfirmTarget) => void }) {
    return (
        <div>
            <h2 className="text-sm font-semibold text-text mb-1 flex items-center gap-2">
                <Gift className="w-4 h-4 text-[var(--accent)]" /> Offers worth running now
            </h2>
            <p className="text-xs text-text-dim mb-3">Each offer shows the exact deal, who it reaches, and why it&apos;s worth it.</p>
            {offers.length === 0 ? (
                <div className="rounded-xl border border-surface-hover bg-[#0f0f0f] p-5 text-sm text-text-dim">
                    No offers to suggest right now — add cost prices and let a few more orders come in, and suggestions will appear here.
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {offers.map((o) => (
                        <div key={o.id} className="rounded-xl border border-surface-hover bg-[#0f0f0f] p-5 flex flex-col">
                            <div className="flex items-start justify-between gap-2">
                                <p className="text-sm font-semibold text-text">{o.title}</p>
                                {o.margin_safe && (
                                    <span title={o.margin_note || "Margin stays healthy"} className="flex items-center gap-1 text-[10px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 rounded px-1.5 py-0.5 whitespace-nowrap">
                                        <ShieldCheck className="w-3 h-3" /> Margin-safe
                                    </span>
                                )}
                            </div>
                            <p className="text-xs text-[#a3a3a3] italic mt-2">“{o.offer_text}”</p>
                            <div className="mt-2 flex items-center gap-1.5 text-[11px] text-text-muted">
                                <Users className="w-3 h-3" /> {o.audience_label}
                            </div>
                            <p className="text-xs text-text-dim mt-2 leading-relaxed flex-1">
                                <span className="text-text-muted font-medium">Why: </span>{o.why}
                            </p>
                            {o.margin_note && <p className="text-[11px] text-text-dim mt-2">💡 {o.margin_note}</p>}
                            <button
                                onClick={() => onPick({ title: o.title, offer_text: o.offer_text, audience_label: o.audience_label, action: o.action })}
                                className="mt-4 self-start flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[var(--accent)] text-bg font-semibold text-sm hover:bg-[var(--accent-hover)] transition-colors"
                            >
                                <Send className="w-3.5 h-3.5" /> Send this
                            </button>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
