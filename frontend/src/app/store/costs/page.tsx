"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { hasModule, loadSetup, type SetupPayload } from "@/lib/storeSetup";

type Cost = { id: number; kind: string; label: string; amount_cents?: number };

export default function CostsPage() {
  const [setup, setSetup] = useState<SetupPayload | null>(null);
  const [rows, setRows] = useState<Cost[]>([]);
  const [kind, setKind] = useState("rent");
  const [label, setLabel] = useState("Rent");
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    const next = await loadSetup();
    setSetup(next);
    if (!hasModule(next, "running-costs")) return;
    const response = await api.get("/api/v1/store/costs");
    setRows(response.data.costs ?? []);
  }

  useEffect(() => {
    refresh().catch(() => setError("Bills could not be loaded."));
  }, []);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await api.post("/api/v1/store/costs", { kind, label, amount_kes: Number(amount) });
      setAmount("");
      await refresh();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "That bill was not saved.");
    }
  }

  if (setup && !hasModule(setup, "running-costs")) {
    return (
      <section className="owner-glass-panel rounded-3xl p-4">
        <h2 className="font-semibold">Bills are locked</h2>
        <Link href="/store/questions" className="mt-4 inline-flex min-h-11 items-center rounded-full bg-white px-4 font-semibold text-black">Open questions</Link>
      </section>
    );
  }

  return (
    <div className="space-y-4">
      <form onSubmit={save} className="owner-glass-panel space-y-3 rounded-3xl p-4">
        <p className="text-sm leading-6 text-zinc-300">Enter the rent, internet, or another bill. After you save, the amount stays with the owner. You will not see the total.</p>
        <label className="block text-sm">Kind
          <select value={kind} onChange={(event) => { setKind(event.target.value); setLabel(event.target.value === "internet" ? "Internet" : event.target.value === "rent" ? "Rent" : ""); }} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/40 px-3">
            <option value="rent">Rent</option>
            <option value="internet">Internet</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label className="block text-sm">Name
          <input required value={label} onChange={(event) => setLabel(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
        </label>
        <label className="block text-sm">Amount (KES)
          <input required inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
        </label>
        {error && <p className="text-sm text-red-300">{error}</p>}
        <button type="submit" className="min-h-11 w-full rounded-full bg-white font-semibold text-black">Save bill</button>
      </form>
      <ul className="space-y-2">
        {rows.map((row) => (
          <li key={row.id} className="owner-glass-panel rounded-3xl px-4 py-3 text-sm">
            <p className="font-semibold">{row.label}</p>
            <p className="text-zinc-400">{row.amount_cents == null ? "Saved. The amount is with the owner." : `${row.amount_cents / 100} KES`}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
