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
  const [plates, setPlates] = useState<{ status: string; message?: string } | null>(null);
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