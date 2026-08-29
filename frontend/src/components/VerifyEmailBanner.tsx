"use client";

import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";

/**
 * Dismissible nudge shown while the logged-in user's email is unverified.
 * Purely informational — verification never gates login or access (see
 * backend models.User.is_email_verified docstring) — so dismissing it is
 * safe and only lasts for the current page load (no localStorage nagging
 * across a whole session; it just isn't a big enough deal to persist that).
 */
export default function VerifyEmailBanner() {
    const { user } = useAuth();
    const [dismissed, setDismissed] = useState(false);
    const [sending, setSending] = useState(false);
    const [sent, setSent] = useState(false);

    if (!user || user.is_email_verified || dismissed) return null;

    const handleResend = async () => {
        setSending(true);
        try {
            await api.post("/api/v1/auth/resend-verification");
            setSent(true);
        } catch {
            // best-effort; nothing actionable to show beyond leaving the button enabled
        } finally {
            setSending(false);
        }
    };

    return (
        <div className="w-full bg-[#1a1a1a] border-b border-[#262626] text-[#a3a3a3] text-xs px-5 py-2 flex items-center justify-between gap-3 flex-wrap">
            <span>
                {sent
                    ? `Verification email sent to ${user.email}.`
                    : `Please verify your email address (${user.email}) to secure your account.`}
            </span>
            <div className="flex items-center gap-3">
                {!sent && (
                    <button
                        onClick={handleResend}
                        disabled={sending}
                        className="text-[var(--accent)] hover:underline disabled:opacity-50"
                    >
                        {sending ? "Sending…" : "Resend email"}
                    </button>
                )}
                <button onClick={() => setDismissed(true)} className="text-[#525252] hover:text-[#737373]">
                    Dismiss
                </button>
            </div>
        </div>
    );
}
