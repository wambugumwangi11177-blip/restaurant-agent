"use client";

// Shared-device PIN quick-switch (tech-debt D16). Lets a waiter "clock in" as
// themselves on a POS tablet that's logged in for the whole shift under one
// device-level account, so orders are attributed to the right person without
// a full re-login. ATTRIBUTION ONLY — this never changes what the device's
// own JWT/role is authorized to do (see backend/routers/auth.py::pin_verify
// and docs/security/threat-model.md T15).

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { User, X, Delete } from "lucide-react";

export interface PinOperator {
    id: number;
    display_name: string;
    role: string;
}

interface RosterEntry {
    id: number;
    display_name: string;
    role: string;
}

export function PinSwitcher({
    currentOperator,
    onSwitch,
}: {
    currentOperator: PinOperator | null;
    onSwitch: (operator: PinOperator) => void;
}) {
    const [open, setOpen] = useState(false);
    const [roster, setRoster] = useState<RosterEntry[]>([]);
    const [selected, setSelected] = useState<RosterEntry | null>(null);
    const [pin, setPin] = useState("");
    const [error, setError] = useState("");
    const [verifying, setVerifying] = useState(false);

    useEffect(() => {
        if (!open) return;
        setSelected(null);
        setPin("");
        setError("");
        api.get("/auth/pin/roster").then((res) => {
            setRoster(res.data?.staff ?? []);
        }).catch(() => setRoster([]));
    }, [open]);

    const digit = (d: string) => {
        setError("");
        setPin((prev) => (prev.length >= 6 ? prev : prev + d));
    };

    const backspace = () => setPin((prev) => prev.slice(0, -1));

    const submit = async () => {
        if (!selected || pin.length < 4) return;
        setVerifying(true);
        setError("");
        try {
            const res = await api.post("/auth/pin/verify", { user_id: selected.id, pin });
            onSwitch(res.data);
            setOpen(false);
        } catch (err) {
            const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
            setError(detail || "Couldn't verify PIN.");
            setPin("");
        }
        setVerifying(false);
    };

    return (
        <>
            <button
                onClick={() => setOpen(true)}
                className="flex items-center gap-1.5 bg-[#1a1a1a] border border-[#262626] rounded-lg px-2.5 py-1 hover:border-[#d4a853]/40 transition-all"
            >
                <User className="w-3 h-3 text-[#d4a853]" />
                <span className="text-[10px] text-[#e5e5e5] font-medium">
                    {currentOperator ? `Serving as: ${currentOperator.display_name}` : "Select staff"}
                </span>
            </button>

            {open && (
                <div
                    className="fixed inset-0 z-[70] flex items-center justify-center p-4 bg-black/60"
                    onClick={() => setOpen(false)}
                >
                    <div
                        className="w-full max-w-xs rounded-xl border border-[#262626] bg-[#0f0f0f] p-4 space-y-3"
                        onClick={(e) => e.stopPropagation()}
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="pin-switch-title"
                    >
                        <div className="flex items-center justify-between">
                            <h3 id="pin-switch-title" className="text-sm font-semibold text-[#e5e5e5]">
                                {selected ? `PIN for ${selected.display_name}` : "Who's serving?"}
                            </h3>
                            <button onClick={() => setOpen(false)} aria-label="Close" className="text-[#525252] hover:text-[#e5e5e5]">
                                <X className="w-4 h-4" />
                            </button>
                        </div>

                        {!selected ? (
                            <div className="grid grid-cols-2 gap-2 max-h-64 overflow-y-auto">
                                {roster.length === 0 ? (
                                    <p className="col-span-2 text-xs text-[#525252] text-center py-4">
                                        No staff have set up a PIN yet.
                                    </p>
                                ) : (
                                    roster.map((s) => (
                                        <button
                                            key={s.id}
                                            onClick={() => setSelected(s)}
                                            className="rounded-lg bg-[#1a1a1a] border border-[#262626] px-3 py-3 text-xs text-[#e5e5e5] hover:border-[#d4a853]/50 transition-all"
                                        >
                                            {s.display_name}
                                        </button>
                                    ))
                                )}
                            </div>
                        ) : (
                            <div className="space-y-3">
                                <div className="flex items-center justify-center gap-2 py-2">
                                    {Array.from({ length: 6 }).map((_, i) => (
                                        <div
                                            key={i}
                                            className={`w-2.5 h-2.5 rounded-full ${i < pin.length ? "bg-[#d4a853]" : "bg-[#262626]"}`}
                                        />
                                    ))}
                                </div>
                                {error && <p className="text-xs text-[#ef4444] text-center">{error}</p>}
                                <div className="grid grid-cols-3 gap-2">
                                    {["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((d) => (
                                        <button
                                            key={d}
                                            onClick={() => digit(d)}
                                            className="rounded-lg bg-[#1a1a1a] border border-[#262626] py-3 text-sm text-[#e5e5e5] hover:border-[#d4a853]/50"
                                        >
                                            {d}
                                        </button>
                                    ))}
                                    <button onClick={() => setSelected(null)} className="rounded-lg bg-[#1a1a1a] border border-[#262626] py-3 text-xs text-[#737373]">
                                        Back
                                    </button>
                                    <button
                                        onClick={() => digit("0")}
                                        className="rounded-lg bg-[#1a1a1a] border border-[#262626] py-3 text-sm text-[#e5e5e5] hover:border-[#d4a853]/50"
                                    >
                                        0
                                    </button>
                                    <button onClick={backspace} aria-label="Backspace" className="rounded-lg bg-[#1a1a1a] border border-[#262626] py-3 flex items-center justify-center text-[#737373]">
                                        <Delete className="w-4 h-4" />
                                    </button>
                                </div>
                                <button
                                    onClick={submit}
                                    disabled={pin.length < 4 || verifying}
                                    className={`w-full py-2.5 rounded-xl text-sm font-semibold transition-all ${pin.length >= 4 && !verifying
                                        ? "bg-[#d4a853] text-black hover:bg-[#c49843]"
                                        : "bg-[#262626] text-[#525252] cursor-not-allowed"
                                        }`}
                                >
                                    {verifying ? "Checking..." : "Confirm"}
                                </button>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </>
    );
}
