"use client";

import { useEffect, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import api from "@/lib/api";

type Dish = {
  id: number;
  name: string;
  price_cents: number;
  cost_cents: number;
  cost_source: string;
  margin_cents: number | null;
  margin_pct: number | null;
};

export default function ElevenDishesPage() {
  const [dishes, setDishes] = useState<Dish[]>([]);
  const [plates, setPlates] = useState<{
    status: string;
    message?: string;
    dishes?: { dish: string; sold: number; expected_handover_units?: number | null; handover_units_recorded?: number }[];
  } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get("/api/v1/eleven/dishes")
      .then((r) => {
        setDishes(r.data.dishes ?? []);
        setPlates(r.data.plates ?? null);
      })
      .catch(() => setError("Dishes could not be loaded."));
  }, []);

  return (
    <OwnerShell title="Dishes">
      {error && <p className="text-sm text-red-300">{error}</p>}
      {plates?.status === "waiting_pos" && (
        <p className="owner-glass-panel mb-3 rounded-2xl p-4 text-sm text-zinc-300">{plates.message}</p>
      )}
      {plates?.status !== "waiting_pos" && (plates?.dishes?.length ?? 0) > 0 && (
        <section className="owner-glass-panel mb-3 space-y-2 rounded-2xl p-4 text-sm text-zinc-300">
          <p className="text-xs uppercase tracking-wide text-zinc-500">Plates (last 7 days)</p>
          {plates?.dishes?.map((row) => (
            <p key={row.dish}>
              <span className="text-zinc-200">{row.dish}</span>
              {" · "}
              {row.sold} sold
              {row.expected_handover_units != null
                ? ` · expected ${row.expected_handover_units} kg from recipes`
                : ""}
              {row.handover_units_recorded != null
                ? ` · ${row.handover_units_recorded} kg handed to kitchen`
                : ""}
            </p>
          ))}
        </section>
      )}
      {dishes.length === 0 && !error && (
        <p className="owner-glass-panel mb-3 rounded-2xl p-4 text-sm text-zinc-300">
          No dishes yet. They appear when the storekeeper adds recipes or you import a menu.
        </p>
      )}
      <ul className="space-y-3">
        {dishes.map((d) => (
          <li key={d.id} className="owner-glass-panel rounded-3xl p-4 text-sm">
            <p className="text-lg font-light text-[var(--text)]">{d.name}</p>
            <p className="mt-1 text-zinc-400">
              Costs {(d.cost_cents / 100).toLocaleString("en-KE")} KES to make · sells at{" "}
              {(d.price_cents / 100).toLocaleString("en-KE")} KES
            </p>
            {d.margin_pct != null && (
              <p className="mt-1 text-[var(--text)]">
                You keep {d.margin_pct}% ({(d.margin_cents ?? 0) / 100} KES)
              </p>
            )}
            <p className="mt-1 text-xs text-zinc-500">Cost from {d.cost_source === "recipe" ? "recipe" : "manual entry"}</p>
          </li>
        ))}
      </ul>
    </OwnerShell>
  );
}