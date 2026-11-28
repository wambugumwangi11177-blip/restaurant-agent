"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { hasModule, loadSetup, type SetupPayload } from "@/lib/storeSetup";

type Status = {
  business_date: string;
  stock_closed: boolean;
  cash_closed: boolean;
  expected_pending?: boolean;
  expected_cash_kes?: number;
  cash_counted_kes?: number;
  mpesa_counted_kes?: number;
  reminder_time?: string;
};

function detailOf(err: unknown, fallback: string) {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  return typeof detail === "string" ? detail : fallback;
}

export default function CashClosePage() {
  const [setup, setSetup] = useState<SetupPayload | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [cash, setCash] = useState("");
  const [mpesa, setMpesa] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSetup()
      .then(async (next) => {
        setSetup(next);
        if (!hasModule(next, "day-close")) return;
        const res = await api.get("/api/v1/store/cash-close/status");
        setStatus(res.data);
      })
      .catch(() => setError("Could not load cash close."))
      .finally(() => setLoading(false));
  }, []);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setSaved("");
    try {
      await api.post("/api/v1/store/cash-close", {
        cash_counted_kes: Number(cash),
        mpesa_counted_kes: Number(mpesa),
        notes,
      });
      setSaved("Saved.");
      const res = await api.get("/api/v1/store/cash-close/status");
      setStatus(res.data);
    } catch (err: unknown) {
      setError(detailOf(err, "Not saved."));
    }
  }

  if (loading) return <p className="text-sm text-zinc-400">Loading…</p>;
  if (setup && !hasModule(setup, "day-close")) {
    return (
      <section className="owner-glass-panel rounded-3xl p-4">
        <h2 className="font-semibold">Locked</h2>
        <p className="mt-2 text-sm text-zinc-300">Opens when your setup says you close the day.</p>
        <Link href="/store/questions" className="mt-4 inline-flex min-h-11 items-center leviii-btn-primary px-4">Questions</Link>
      </section>
    );
  }

  return (
    <div className="space-y-4">
      {status && (
        <section className="owner-glass-panel rounded-3xl p-4 text-sm text-zinc-300">
          <p>Stock close today: {status.stock_closed ? "Done" : "Still open"}</p>
          <p>Cash close today: {status.cash_closed ? "Done" : "Still open"}</p>
          {status.expected_pending && !status.cash_closed && (
            <p className="mt-2 text-zinc-400">Expected cash from the till is not connected yet — record what you counted.</p>
          )}
          {!status.expected_pending && status.expected_cash_kes != null && !status.cash_closed && (
            <p className="mt-2">Expected cash in drawer: {status.expected_cash_kes.toLocaleString()} KES</p>
          )}
        </section>
      )}
      {status?.cash_closed ? (
        <p className="text-sm text-zinc-200">Today&apos;s cash and M-Pesa are recorded.</p>
      ) : (
        <form onSubmit={save} className="owner-glass-panel space-y-3 rounded-3xl p-4">
          <p className="text-sm text-zinc-300">Record physical cash and M-Pesa — store staff never see these totals.</p>
          <label className="block text-sm">Cash counted (KES)
            <input required inputMode="decimal" value={cash} onChange={(e) => setCash(e.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
          </label>
          <label className="block text-sm">M-Pesa counted (KES)
            <input required inputMode="decimal" value={mpesa} onChange={(e) => setMpesa(e.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
          </label>
          <label className="block text-sm">Notes
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} className="mt-1 min-h-20 w-full rounded-2xl border border-white/15 bg-black/30 px-3 py-2" />
          </label>
          {error && <p className="text-sm text-red-300">{error}</p>}
          {saved && <p className="text-sm text-zinc-200">{saved}</p>}
          <button type="submit" className="min-h-11 w-full leviii-btn-primary">Save cash close</button>
        </form>
      )}
    </div>
  );
}