"use client";

import { useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export default function ChangePinPanel() {
  const { refreshUser } = useAuth();
  const [pin, setPin] = useState("");
  const [confirm, setConfirm] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setMessage("");
    setError("");
    if (!/^\d{4}$/.test(pin)) {
      setError("PIN must be 4 digits.");
      return;
    }
    if (pin !== confirm) {
      setError("PINs did not match.");
      return;
    }
    setBusy(true);
    try {
      await api.post("/api/v1/auth/pin/set", { pin });
      await refreshUser();
      setPin("");
      setConfirm("");
      setMessage("PIN updated.");
    } catch (err: unknown) {
      const ax = err as { response?: { data?: { detail?: string } } };
      setError(ax.response?.data?.detail ?? "Could not update PIN.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <label className="block text-sm">
        New PIN (4 digits)
        <input
          inputMode="numeric"
          pattern="[0-9]{4}"
          maxLength={4}
          value={pin}
          onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 4))}
          className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3 tracking-widest"
          autoComplete="off"
        />
      </label>
      <label className="block text-sm">
        Confirm PIN
        <input
          inputMode="numeric"
          pattern="[0-9]{4}"
          maxLength={4}
          value={confirm}
          onChange={(e) => setConfirm(e.target.value.replace(/\D/g, "").slice(0, 4))}
          className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3 tracking-widest"
          autoComplete="off"
        />
      </label>
      <button
        type="submit"
        disabled={busy}
        className="min-h-11 rounded-full bg-white px-4 font-semibold text-black disabled:opacity-50"
      >
        {busy ? "Saving…" : "Change PIN"}
      </button>
      {message && <p className="text-sm text-green-300">{message}</p>}
      {error && <p className="text-sm text-red-300">{error}</p>}
    </form>
  );
}