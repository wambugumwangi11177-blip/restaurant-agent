"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { AccountDiagram } from "@/components/store/diagrams";
import { loadSetup, stepById, type SetupPayload } from "@/lib/storeSetup";

export default function StoreAccountPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [setup, setSetup] = useState<SetupPayload | null>(null);
  const done = stepById(setup, "account")?.state === "done" || (user?.must_change_password === false && user?.has_pin === true);

  useEffect(() => {
    loadSetup().then(setSetup).catch(() => undefined);
  }, []);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    if (!/^\d{4}$/.test(pin)) {
      setError("The PIN is 4 digits.");
      return;
    }
    setSaving(true);
    try {
      await api.post("/api/v1/staff-setup/account", {
        current_password: currentPassword,
        new_password: newPassword,
        pin,
      });
      router.replace("/store/recipes");
      router.refresh();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "That password or PIN was not saved.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      <section className="owner-glass-panel rounded-3xl p-4">
        <AccountDiagram />
        <p className="text-sm leading-6 text-zinc-300">
          Replace the password you were given, then choose a 4-digit PIN only you know. The PIN uses the same lockout as the shared tablet.
        </p>
      </section>
      {done ? (
        <p className="owner-glass-panel rounded-3xl p-4 text-sm text-zinc-200">
          Your password and PIN are already saved. Recipe entry is open.
        </p>
      ) : (
        <form onSubmit={onSubmit} className="owner-glass-panel space-y-3 rounded-3xl p-4">
          <label className="block text-sm">
            Current password
            <input
              type="password"
              required
              autoComplete="current-password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
              className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3"
            />
          </label>
          <label className="block text-sm">
            New password
            <input
              type="password"
              required
              autoComplete="new-password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3"
            />
          </label>
          <label className="block text-sm">
            4-digit PIN
            <input
              inputMode="numeric"
              autoComplete="off"
              pattern="\d{4}"
              maxLength={4}
              required
              value={pin}
              onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, 4))}
              className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3 tracking-[0.4em]"
            />
          </label>
          {error && <p className="text-sm text-red-300">{error}</p>}
          <button type="submit" disabled={saving} className="min-h-11 w-full rounded-full bg-white font-semibold text-black disabled:opacity-60">
            {saving ? "Saving…" : "Save password and PIN"}
          </button>
        </form>
      )}
    </div>
  );
}
