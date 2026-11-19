"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { markPinUnlocked } from "@/lib/appLock";
import PinKeypad from "@/components/auth/PinKeypad";

export default function SetPinScreen({
  displayName,
  onDone,
}: {
  displayName: string;
  onDone: () => void;
}) {
  const { refreshUser } = useAuth();
  const [step, setStep] = useState<"enter" | "confirm">("enter");
  const [first, setFirst] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const pin = step === "enter" ? first : confirm;

  useEffect(() => {
    if (pin.length < 4) return;
    if (step === "enter") {
      setStep("confirm");
      return;
    }
    if (confirm !== first) {
      setError("PINs did not match. Try again.");
      setFirst("");
      setConfirm("");
      setStep("enter");
      return;
    }
    let cancelled = false;
    (async () => {
      setBusy(true);
      setError("");
      try {
        await api.post("/api/v1/auth/pin/set", { pin: confirm });
        await refreshUser();
        markPinUnlocked();
        if (!cancelled) onDone();
      } catch (err: unknown) {
        const ax = err as { response?: { data?: { detail?: string } } };
        if (!cancelled) {
          setError(ax.response?.data?.detail ?? "Could not save PIN");
          setFirst("");
          setConfirm("");
          setStep("enter");
        }
      } finally {
        if (!cancelled) setBusy(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pin, step, confirm, first, refreshUser, onDone]);

  return (
    <div className="fixed inset-0 z-[200] flex min-h-dvh flex-col items-center justify-center bg-[#0a0a0a] px-4">
      <div className="w-full max-w-sm rounded-3xl border border-white/15 bg-[#16161a] p-6 shadow-lg">
        <h1 className="text-center text-xl font-semibold text-white">Choose a PIN for {displayName}</h1>
        <p className="mt-2 text-center text-sm text-zinc-400">
          {step === "enter" ? "Pick 4 digits only you know." : "Enter it again to confirm."}
        </p>
        <div className="mt-6 flex justify-center gap-3">
          {[0, 1, 2, 3].map((i) => (
            <span
              key={i}
              className={`h-3 w-3 rounded-full ${pin.length > i ? "bg-white" : "bg-white/20"}`}
            />
          ))}
        </div>
        {error && <p className="mt-4 text-center text-sm text-red-300">{error}</p>}
        <div className="mt-6">
          <PinKeypad
            value={pin}
            onChange={step === "enter" ? setFirst : setConfirm}
            disabled={busy}
            ariaLabel="Set PIN keypad"
          />
        </div>
      </div>
    </div>
  );
}