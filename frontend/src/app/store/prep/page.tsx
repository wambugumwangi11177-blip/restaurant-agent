"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";

type Row = { dish: string; date: string; ingredients: { ingredient: string; quantity: number; issue_qty: number; unit: string; kitchen_has?: number }[] };

export default function PrepListPage() {
  const [data, setData] = useState<{ date: string; rows: Row[]; message?: string } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get("/api/v1/store/prep/list")
      .then((r) => setData(r.data))
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        if (detail === "questionnaire_required") {
          setError("Finish the setup questions first. Prep quantities appear after Jack names dishes and handovers.");
          return;
        }
        setError(typeof detail === "string" ? detail : "Prep list could not load.");
      });
  }, []);

  if (error) return <p className="text-sm text-red-300">{error}</p>;
  if (!data) return <p className="text-sm text-zinc-400">Loading prep list…</p>;

  return (
    <section className="owner-glass-panel space-y-3 rounded-3xl p-4">
      <h1 className="text-lg font-semibold">Prep for {data.date}</h1>
      <p className="text-sm text-zinc-400">Usual plates from recent handovers × recipe (with yield), minus what the kitchen already has.</p>
      {data.message && data.rows.length === 0 ? (
        <p className="text-sm text-zinc-300">{data.message}</p>
      ) : data.rows.length === 0 ? (
        <p className="text-sm text-zinc-300">Add recipes and handover history to see prep quantities.</p>
      ) : (
        <ul className="space-y-3">
          {data.rows.map((row) => (
            <li key={row.dish} className="rounded-2xl border border-white/10 bg-black/30 p-3 text-sm">
              <p className="font-medium text-zinc-200">{row.dish}</p>
              <ul className="mt-2 space-y-1 text-zinc-400">
                {row.ingredients
                  .filter((ing) => ing.issue_qty > 0)
                  .map((ing) => (
                  <li key={ing.ingredient}>
                    Issue {ing.issue_qty} {ing.unit} {ing.ingredient}
                    {ing.kitchen_has != null && ing.kitchen_has > 0 ? ` (kitchen has ${ing.kitchen_has})` : ""}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}