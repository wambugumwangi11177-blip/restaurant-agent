"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { markPinUnlocked } from "@/lib/appLock";
import PinKeypad from "@/components/auth/PinKeypad";
import "@/styles/owner-glass.css";

export default function LockScreen({
  displayName,
  onUnlocked,
}: {
  displayName: string;
  onUnlocked: () => void;
}) {
  const { logout } = useAuth();
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (pin.length < 4) return;
    let cancelled = false;
    (async () => {
      setBusy(true);
      setError("");
      try {
        await api.post("/api/v1/auth/pin/unlock", { pin });
        if (!cancelled) {
          markPinUnlocked();
          setPin("");
          onUnlocked();
        }
      } catch (err: unknown) {
        if (cancelled) return;
        const ax = err as { response?: { data?: { detail?: string | { code?: string; message?: string } } } };
        const detail = ax.response?.data?.detail;
        const code = typeof detail === "object" && detail?.code;
        if (code === "PIN_LOCKOUT" || code === "PASSWORD_REQUIRED") {
          clearPinState();
          await logout();
          window.location.href = "/login";
          return;
        }
        setError(typeof detail === "string" ? detail : "Incorrect PIN");
        setPin("");
      } finally {
        if (!cancelled) setBusy(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pin, logout, onUnlocked]);

  function clearPinState() {
    setPin("");
  }

  return (
    <div className="owner-glass-theme fixed inset-0 z-[200] flex min-h-dvh flex-col items-center justify-center bg-[#0a0a0a] px-4 pb-[env(safe-area-inset-bottom)] pt-[env(safe-area-inset-top)]">
      <div className="owner-glass-panel w-full max-w-sm rounded-3xl p-6">
        <p className="text-center text-xs uppercase tracking-[0.2em] text-zinc-500">LEVIII</p>
        <h1 className="mt-2 text-center text-2xl font-semibold text-white">{displayName}</h1>
        <p className="mt-1 text-center text-sm text-zinc-400">Enter your 4-digit PIN</p>
        <div className="mt-6 flex justify-center gap-3" aria-live="polite">
          {[0, 1, 2, 3].map((i) => (
            <span
              key={i}
              className={`h-3 w-3 rounded-full ${pin.length > i ? "bg-white" : "bg-white/20"}`}
            />
          ))}
        </div>
        {error && <p className="mt-4 text-center text-sm text-red-300">{error}</p>}
        <div className="mt-6">
          <PinKeypad value={pin} onChange={setPin} disabled={busy} />
        </div>
        <Link
          href="/login"
          onClick={() => logout()}
          className="mt-6 block text-center text-sm text-zinc-400 underline-offset-2 hover:text-zinc-200 hover:underline"
        >
          Not you? Sign in with password
        </Link>
      </div>
    </div>
  );
}