"use client";

import { useEffect, useState } from "react";
import { Users, ArrowLeft } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { getErrorMessage } from "@/lib/errors";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";

interface RosterEntry {
    user_id: number;
    name: string;
    role_title: string | null;
    staff_role: string | null;
}

/**
 * Shared-device quick-switch (audit remediation, Tier 5 item 12) — no PIN
 * login existed at all before this; every staff member needed a full
 * email+password re-auth to use a shared POS/KDS tablet mid-shift. Two
 * steps: pick a teammate from the roster (only people who've opted into a
 * PIN appear here — see GET /auth/quick-switch/roster), then enter their
 * PIN. No existing PIN-pad component to build on (none existed anywhere in
 * this frontend) — a single numeric input is deliberately simpler than a
 * custom on-screen keypad: mobile browsers already show a numeric keyboard
 * for inputMode="numeric", so a bespoke keypad would just duplicate that.
 */
export default function QuickSwitchModal({
    onClose,
    onSetUpOwnPin,
}: {
    onClose: () => void;
    onSetUpOwnPin: () => void;
}) {
    const { loginWithPin } = useAuth();
    const [roster, setRoster] = useState<RosterEntry[]>([]);
    const [loading, setLoading] = useState(true);
    const [selected, setSelected] = useState<RosterEntry | null>(null);
    const [pin, setPin] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState("");

    useEffect(() => {
        api.get("/api/v1/auth/quick-switch/roster")
            .then((res) => setRoster(res.data))
            .catch(() => setRoster([]))
            .finally(() => setLoading(false));
    }, []);

    const handlePinSubmit = async () => {
        if (!selected || pin.length < 4) return;
        setSubmitting(true);
        setError("");
        try {
            await loginWithPin(selected.user_id, pin);
            onClose();
        } catch (err) {
            setError(getErrorMessage(err, "That PIN didn't work — try again."));
            setPin("");
        }
        setSubmitting(false);
    };

    return (
        <Modal label={selected ? `Enter PIN for ${selected.name}` : "Switch user"} onClose={onClose}>
            {!selected ? (
                <div className="space-y-2">
                    {loading && <p className="text-xs text-[var(--text-dim)]">Loading teammates…</p>}
                    {!loading && roster.length === 0 && (
                        <p className="text-xs text-[var(--text-dim)]">
                            No teammates have set up a quick-switch PIN yet. Set one from your
                            account settings, then it&apos;ll show up here for others.
                        </p>
                    )}
                    {roster.map((r) => (
                        <button
                            key={r.user_id}
                            onClick={() => { setSelected(r); setError(""); }}
                            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg border border-[var(--border)] hover:border-[var(--accent)]/50 hover:bg-[var(--surface-hover)] text-left transition-colors"
                        >
                            <Users className="w-4 h-4 text-[var(--accent)] shrink-0" />
                            <div className="min-w-0">
                                <p className="text-sm text-[var(--text)] truncate">{r.name}</p>
                                {r.role_title && (
                                    <p className="text-xs text-[var(--text-dim)] truncate">{r.role_title}</p>
                                )}
                            </div>
                        </button>
                    ))}
                    {!loading && (
                        <button
                            onClick={onSetUpOwnPin}
                            className="w-full text-center text-xs text-[var(--text-dim)] hover:text-[var(--accent)] pt-2"
                        >
                            Not listed? Set up your own quick-switch PIN
                        </button>
                    )}
                </div>
            ) : (
                <div className="space-y-3">
                    <button
                        onClick={() => { setSelected(null); setPin(""); setError(""); }}
                        className="flex items-center gap-1 text-xs text-[var(--text-dim)] hover:text-[var(--text)]"
                    >
                        <ArrowLeft className="w-3 h-3" /> Back
                    </button>
                    <input
                        type="password"
                        inputMode="numeric"
                        autoComplete="off"
                        maxLength={6}
                        placeholder="PIN"
                        value={pin}
                        autoFocus
                        onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
                        onKeyDown={(e) => { if (e.key === "Enter") handlePinSubmit(); }}
                        className="w-full text-center text-2xl tracking-[0.5em] bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg py-3 text-[var(--text)] focus:border-[var(--accent)] focus:outline-none"
                    />
                    {error && <p className="text-xs text-[var(--danger)]">{error}</p>}
                    <Button
                        variant="primary"
                        className="w-full"
                        disabled={pin.length < 4 || submitting}
                        onClick={handlePinSubmit}
                    >
                        {submitting ? "Checking…" : "Switch"}
                    </Button>
                </div>
            )}
        </Modal>
    );
}
