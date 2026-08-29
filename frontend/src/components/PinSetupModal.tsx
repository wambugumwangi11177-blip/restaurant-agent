"use client";

import { useState } from "react";
import api from "@/lib/api";
import { getErrorMessage } from "@/lib/errors";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";

/**
 * Self-service opt-in for the shared-device quick-switch PIN (audit
 * remediation, Tier 5 item 12) — see QuickSwitchModal for the switch side.
 * A user only appears on a teammate's roster after setting one here.
 */
export default function PinSetupModal({ onClose }: { onClose: () => void }) {
    const [pin, setPin] = useState("");
    const [confirmPin, setConfirmPin] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState("");
    const [success, setSuccess] = useState(false);

    const handleSubmit = async () => {
        if (pin !== confirmPin) {
            setError("PINs don't match.");
            return;
        }
        setSubmitting(true);
        setError("");
        try {
            await api.post("/api/v1/auth/pin/set", { pin });
            setSuccess(true);
            setTimeout(onClose, 1200);
        } catch (err) {
            setError(getErrorMessage(err, "Couldn't set that PIN — try again."));
        }
        setSubmitting(false);
    };

    return (
        <Modal label="Set up your quick-switch PIN" onClose={onClose}>
            {success ? (
                <p className="text-sm text-[var(--accent)]">PIN saved — teammates can now switch to you.</p>
            ) : (
                <div className="space-y-3">
                    <p className="text-xs text-[var(--text-dim)]">
                        A 4-6 digit PIN lets teammates switch to your account on a shared
                        device without typing your password.
                    </p>
                    <input
                        type="password"
                        inputMode="numeric"
                        autoComplete="off"
                        maxLength={6}
                        placeholder="New PIN"
                        value={pin}
                        autoFocus
                        onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
                        className="w-full text-center text-xl tracking-[0.4em] bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg py-2.5 text-[var(--text)] focus:border-[var(--accent)] focus:outline-none"
                    />
                    <input
                        type="password"
                        inputMode="numeric"
                        autoComplete="off"
                        maxLength={6}
                        placeholder="Confirm PIN"
                        value={confirmPin}
                        onChange={(e) => setConfirmPin(e.target.value.replace(/\D/g, ""))}
                        onKeyDown={(e) => { if (e.key === "Enter") handleSubmit(); }}
                        className="w-full text-center text-xl tracking-[0.4em] bg-[var(--surface-hover)] border border-[var(--border)] rounded-lg py-2.5 text-[var(--text)] focus:border-[var(--accent)] focus:outline-none"
                    />
                    {error && <p className="text-xs text-[var(--danger)]">{error}</p>}
                    <Button
                        variant="primary"
                        className="w-full"
                        disabled={pin.length < 4 || submitting}
                        onClick={handleSubmit}
                    >
                        {submitting ? "Saving…" : "Save PIN"}
                    </Button>
                </div>
            )}
        </Modal>
    );
}
