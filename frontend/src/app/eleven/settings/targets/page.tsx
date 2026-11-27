"use client";

import { useEffect, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import api from "@/lib/api";

export default function SettingsTargetsPage() {
  const [food, setFood] = useState("32");
  const [sales, setSales] = useState("1200000");
  const [par, setPar] = useState("7");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.get("/api/v1/eleven/settings/targets").then((r) => {
      setFood(String(r.data.food_cost_target_pct ?? 32));
      setSales(String(r.data.monthly_sales_target_kes ?? 1200000));
      setPar(String(r.data.default_par_days ?? 7));
    });
  }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    await api.patch("/api/v1/eleven/settings/targets", {
      food_cost_target_pct: Number(food),
      monthly_sales_target_kes: Number(sales),
      default_par_days: Number(par),
    });
    setMsg("Saved.");
  }

  return (
    <OwnerShell title="Targets">
      <form onSubmit={save} className="owner-glass-panel space-y-4 p-5">
        <label className="block text-sm">
          Food cost target %
          <input className="mt-1 w-full rounded-2xl border border-white/15 bg-black/30 px-3 py-2" value={food} onChange={(e) => setFood(e.target.value)} />
        </label>
        <label className="block text-sm">
          Monthly sales target (KES)
          <input className="mt-1 w-full rounded-2xl border border-white/15 bg-black/30 px-3 py-2" value={sales} onChange={(e) => setSales(e.target.value)} />
        </label>
        <label className="block text-sm">
          Default par days
          <input className="mt-1 w-full rounded-2xl border border-white/15 bg-black/30 px-3 py-2" value={par} onChange={(e) => setPar(e.target.value)} />
        </label>
        <button type="submit" className="leviii-btn-primary px-4 py-2">Save</button>
        {msg && <p className="text-sm text-zinc-300">{msg}</p>}
      </form>
    </OwnerShell>
  );
}