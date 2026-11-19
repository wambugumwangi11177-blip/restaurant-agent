"use client";

import { useEffect, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import Link from "next/link";
import { GlassCard, SectionLabel, WaitingNotice } from "@/components/eleven/EmptyPanels";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useRouter } from "next/navigation";

type LoginRow = {
  id: number;
  email: string;
  staff_role: string | null;
  password_reset_required: boolean;
  has_password: boolean;
};

export default function ElevenSettingsPage() {
  const { logout } = useAuth();
  const router = useRouter();
  const [qty, setQty] = useState("5");
  const [saved, setSaved] = useState("");
  const [logins, setLogins] = useState<LoginRow[]>([]);
  const [handover, setHandover] = useState<{ email: string; code: string; expires_at: string } | null>(null);
  const [resetBusy, setResetBusy] = useState<number | null>(null);

  useEffect(() => {
    api.get("/api/v1/store/policy").then((response) => {
      setQty(String(response.data.spoilage_approval_qty ?? 5));
    }).catch(() => setSaved(""));
    api.get<LoginRow[]>("/api/v1/eleven/logins").then((r) => setLogins(r.data)).catch(() => setLogins([]));
  }, []);

  async function resetSignIn(row: LoginRow) {
    const who = row.staff_role === "OWNER" ? "owner" : row.staff_role === "STOCKKEEPER" ? "Jack (store)" : "accountant";
    const ok = window.confirm(
      `Reset sign-in for ${row.email}?\n\nTheir old password stops working. You will get a one-time 6-digit code to hand to ${who}.`,
    );
    if (!ok) return;
    setResetBusy(row.id);
    try {
      const res = await api.post<{ handover_code: string; expires_at: string; must_log_out: boolean; email: string }>(
        `/api/v1/eleven/logins/${row.id}/reset-sign-in`,
      );
      setHandover({ email: res.data.email, code: res.data.handover_code, expires_at: res.data.expires_at });
      const refreshed = await api.get<LoginRow[]>("/api/v1/eleven/logins");
      setLogins(refreshed.data);
      if (res.data.must_log_out) {
        await logout();
        router.replace("/login");
      }
    } finally {
      setResetBusy(null);
    }
  }

  function roleLabel(role: string | null) {
    if (role === "OWNER") return "Owner";
    if (role === "STOCKKEEPER") return "Jack (store)";
    if (role === "CONTROLLER") return "Accountant";
    return role ?? "Login";
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    await api.put("/api/v1/store/policy", { spoilage_approval_qty: Number(qty) });
    setSaved("Saved. Smaller amounts are only reported.");
  }

  return (
    <OwnerShell title="Settings">
      <SectionLabel>Logins</SectionLabel>
      <GlassCard>
        <p className="text-sm text-zinc-400 mb-3">
          Reset sign-in when handing the app to the real owner, Jack, or accountant. You get a one-time code (72 hours) to pass to them.
        </p>
        {handover && (
          <div className="mb-4 rounded-2xl border border-amber-400/40 bg-amber-500/10 p-4 text-sm">
            <p className="font-semibold text-amber-100">Handover code for {handover.email}</p>
            <p className="mt-2 text-3xl font-mono tracking-[0.3em] text-white">{handover.code}</p>
            <p className="mt-2 text-zinc-400">Valid until {new Date(handover.expires_at).toLocaleString()}. Shown once — copy it now.</p>
          </div>
        )}
        <ul className="space-y-2">
          {logins.map((row) => (
            <li key={row.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-white/10 px-3 py-2">
              <div>
                <p className="text-sm font-medium text-white">{roleLabel(row.staff_role)}</p>
                <p className="text-xs text-zinc-500">{row.email}</p>
                {row.password_reset_required && <p className="text-xs text-amber-300">Waiting for new password</p>}
              </div>
              <button
                type="button"
                disabled={resetBusy === row.id}
                onClick={() => resetSignIn(row)}
                className="min-h-10 rounded-full border border-white/20 px-3 text-sm text-white hover:bg-white/10 disabled:opacity-50"
              >
                {resetBusy === row.id ? "Resetting…" : "Reset sign-in"}
              </button>
            </li>
          ))}
        </ul>
        {logins.length === 0 && <WaitingNotice>No logins listed yet.</WaitingNotice>}
      </GlassCard>
      <SectionLabel>Your till</SectionLabel>
      <GlassCard>
        <Link href="/eleven/settings/till" className="inline-flex min-h-11 items-center text-sm text-white underline">Review QuickSell receipt and parser evidence</Link>
      </GlassCard>
      <SectionLabel>Permits</SectionLabel>
      <GlassCard>
        <WaitingNotice>Add your fire, food handling, and liquor licences to see days left and reminders.</WaitingNotice>
      </GlassCard>
      <SectionLabel>Your numbers</SectionLabel>
      <GlassCard>
        <form onSubmit={save} className="space-y-3">
          <label className="block text-sm">Waste or a count gap that waits for you
            <input inputMode="decimal" value={qty} onChange={(event) => setQty(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
          </label>
          <button type="submit" className="min-h-11 rounded-full bg-white px-4 font-semibold text-black">Save</button>
          {saved && <p className="text-sm text-zinc-300">{saved}</p>}
        </form>
        <WaitingNotice>Margin and cash-gap reminders stay quiet until the till is live.</WaitingNotice>
      </GlassCard>
    </OwnerShell>
  );
}
