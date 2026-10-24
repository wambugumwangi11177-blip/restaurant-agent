"use client";
import { useEffect, useState } from "react";
import api from "@/lib/api";
import Bars from "@/components/charts/Bars";
import { kes } from "@/lib/owner/format";

type Branch = { name: string; sales: number; food_cost_pct: number | null; wages_pct: number | null; cash_gap_kes: number | null; cash_note: string; stock_gaps_kes: number | null; stock_checks: number; below_menu_estimate_kes_month: number };

export default function BranchReview() {
  const [data, setData] = useState<{ branches: Branch[]; note: string } | null>(null);
  const [error, setError] = useState("");
  const [numbers, setNumbers] = useState(false);
  useEffect(() => {
    api.get("/api/v1/owner/planning/branches").then((r) => setData(r.data)).catch(() => setError("Could not compare branches. Retry after checking the connection."));
  }, []);
  return (
    <section id="branch-review" className="space-y-4 rounded-xl border border-[var(--v-border)] bg-[var(--v-bg)] p-4">
      <h2 className="text-xl font-semibold">Branches side by side</h2>
      {error && <p role="alert">{error}</p>}
      {!data && !error && <p className="text-sm text-[var(--v-muted-foreground)]">Loading the branches you can see…</p>}
      {data && (data.branches ?? []).length === 0 && <p className="text-sm text-[var(--v-muted-foreground)]">A second branch will appear beside this one once it is recording sales.</p>}
      {data && (data.branches ?? []).length > 0 && (
        <>
          <p className="text-sm">{data.note}</p>
          <Bars label="Sales by branch" bars={data.branches.map((b) => ({ key: b.name, label: b.name.slice(0, 8), value: b.sales, title: `${b.name}: ${kes(b.sales)}` }))} />
          <button type="button" className="min-h-10 text-[11px] font-bold text-[var(--v-primary)]" aria-expanded={numbers} onClick={() => setNumbers((v) => !v)}>{numbers ? "Hide numbers" : "Show numbers"}</button>
          {numbers && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead><tr>{["Branch", "Sales", "Ingredients", "Wages", "Cash difference", "Stock count shortages", "Below-menu estimate / month"].map((x) => <th className="p-2" key={x}>{x}</th>)}</tr></thead>
                <tbody>{data.branches.map((b) => (
                  <tr key={b.name}><th className="p-2">{b.name}</th><td className="p-2">{kes(b.sales)}</td><td className="p-2">{b.food_cost_pct === null ? "No data" : `${b.food_cost_pct}%`}</td><td className="p-2">{b.wages_pct === null ? "No data" : `${b.wages_pct}%`}</td><td className="p-2">{b.cash_gap_kes === null ? "Not combined" : kes(b.cash_gap_kes)}<p>{b.cash_note}</p></td><td className="p-2">{b.stock_gaps_kes === null ? "No counts" : kes(b.stock_gaps_kes)} · {b.stock_checks} checks</td><td className="p-2">{kes(b.below_menu_estimate_kes_month)}</td></tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
