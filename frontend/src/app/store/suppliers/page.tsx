"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { hasModule, loadSetup, type SetupPayload } from "@/lib/storeSetup";

type Supplier = { id: number; name: string; phone: string; brings: string; arrival?: string; arrival_label?: string };

const BRINGS = ["Main food", "Alcohol", "Both", "Other"];
const ARRIVALS = [
  { value: "phone", label: "Phone order" },
  { value: "scheduled", label: "Scheduled delivery" },
  { value: "pickup", label: "Pickup" },
  { value: "other", label: "Other" },
];

export default function SuppliersPage() {
  const [setup, setSetup] = useState<SetupPayload | null>(null);
  const [rows, setRows] = useState<Supplier[]>([]);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [brings, setBrings] = useState("Main food");
  const [arrival, setArrival] = useState("phone");
  const [error, setError] = useState("");

  async function refresh() {
    const next = await loadSetup();
    setSetup(next);
    if (hasModule(next, "suppliers")) {
      const response = await api.get("/api/v1/store/suppliers");
      setRows(response.data);
    }
  }

  useEffect(() => {
    refresh().catch(() => setError("Suppliers could not be loaded."));
  }, []);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await api.post("/api/v1/store/suppliers", { name, phone, brings, arrival });
      setName("");
      setPhone("");
      await refresh();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "That supplier was not saved.");
    }
  }

  if (setup && !hasModule(setup, "suppliers")) {
    return (
      <section className="owner-glass-panel rounded-3xl p-4">
        <h2 className="font-semibold">Suppliers are locked</h2>
        <p className="mt-2 text-sm text-zinc-300">Answer the supplier question first.</p>
        <Link href="/store/questions" className="mt-4 inline-flex min-h-11 items-center rounded-full bg-white px-4 font-semibold text-black">Open questions</Link>
      </section>
    );
  }

  return (
    <div className="space-y-4">
      <form onSubmit={save} className="owner-glass-panel space-y-3 rounded-3xl p-4">
        <label className="block text-sm">Name
          <input required value={name} onChange={(event) => setName(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
        </label>
        <label className="block text-sm">Phone
          <input value={phone} onChange={(event) => setPhone(event.target.value)} inputMode="tel" className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
        </label>
        <label className="block text-sm">What they bring
          <select value={brings} onChange={(event) => setBrings(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/40 px-3">
            {BRINGS.map((option) => <option key={option}>{option}</option>)}
          </select>
        </label>
        <label className="block text-sm">How supplies arrive
          <select value={arrival} onChange={(event) => setArrival(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/40 px-3">
            {ARRIVALS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        {error && <p className="text-sm text-red-300">{error}</p>}
        <button type="submit" className="min-h-11 w-full rounded-full bg-white font-semibold text-black">Save supplier</button>
      </form>
      <ul className="space-y-2">
        {rows.map((row) => (
          <li key={row.id} className="owner-glass-panel rounded-3xl px-4 py-3 text-sm">
            <p className="font-semibold">{row.name}</p>
            <p className="text-zinc-400">{row.brings}{row.arrival_label ? ` · ${row.arrival_label}` : ""}{row.phone ? ` · ${row.phone}` : ""}</p>
          </li>
        ))}
      </ul>
      <Link href="/store/questions" className="block text-center text-sm text-zinc-400">Next question</Link>
    </div>
  );
}
