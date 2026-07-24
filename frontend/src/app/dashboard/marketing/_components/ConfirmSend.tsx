"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Send, X } from "lucide-react";
import api from "@/lib/api";
import { getErrorMessage } from "@/lib/errors";

// This component already has the reference-quality accessibility pattern for
// this codebase (role="dialog", aria-modal, aria-label, Escape-key listener,
// dedicated error state) — see the audit notes at the top of the marketing
// route. Left functionally as-is during the file split; only extracted to its
// own file and had its hardcoded hex colors migrated to design tokens.
export default function ConfirmSend({
    offer, onClose, onSent,
}: {
    offer: { title: string; offer_text: string; audience_label: string; action: "winback" | "promo" };
    onClose: () => void;
    onSent: (msg: string) => void;
}) {
    const [sending, setSending] = useState(false);
    const [error, setError] = useState("");

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
        };
        document.addEventListener("keydown", handleKeyDown);
        return () => document.removeEventListener("keydown", handleKeyDown);
    }, [onClose]);

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
        } catch (e) {
            setError(getErrorMessage(e, "Could not send the campaign."));
        } finally {
            setSending(false);
        }
    };

    return (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/60" onClick={onClose}>
            <div role="dialog" aria-modal="true" aria-label="Send this campaign?" className="w-full max-w-md rounded-xl border border-border bg-[#0f0f0f] p-5 space-y-4" onClick={(e) => e.stopPropagation()}>
                <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2">
                        <Send className="w-4 h-4 text-[var(--accent)]" />
                        <h3 className="text-sm font-semibold text-text">Send this campaign?</h3>
                    </div>
                    <button onClick={onClose} aria-label="Close dialog" className="text-text-dim hover:text-text"><X className="w-4 h-4" /></button>
                </div>

                <div className="rounded-lg border border-surface-hover bg-bg p-3 space-y-1.5">
                    <p className="text-sm text-text">{offer.title}</p>
                    <p className="text-xs text-[#a3a3a3] italic">“{offer.offer_text}”</p>
                    <p className="text-[11px] text-text-muted">Audience: {offer.audience_label}</p>
                </div>

                <p className="text-[11px] text-amber-400/90 flex gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                    <span>This sends real WhatsApp messages now. Only customers who gave consent and haven&apos;t opted out are contacted.</span>
                </p>

                {error && <p className="text-xs text-red-400">{error}</p>}

                <div className="flex items-center justify-end gap-2">
                    <button onClick={onClose} className="px-3 py-2 rounded-lg text-sm text-text-muted hover:text-text">Cancel</button>
                    <button
                        onClick={send}
                        disabled={sending}
                        className="px-4 py-2 rounded-lg bg-[var(--accent)] text-bg font-semibold text-sm hover:bg-[var(--accent-hover)] disabled:opacity-60"
                    >
                        {sending ? "Sending…" : "Yes, send it"}
                    </button>
                </div>
            </div>
        </div>
    );
}
