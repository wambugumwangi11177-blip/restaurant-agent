"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { loadSetup, stepById, type SetupPayload } from "@/lib/storeSetup";

type Item = { id: number; item_name: string; quantity: number; unit: string };

export default function StoreStockPage() {
  const [setup, setSetup] = useState<SetupPayload | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    loadSetup()
      .then(async (next) => {
        setSetup(next);
        if (next.app_unlocked) {
          const response = await api.get("/api/v1/inventory/");
          setItems(response.data);
        }
      })
      .catch(() => setError("Stock could not be loaded."));
  }, []);

  const recipes = stepById(setup, "recipes");
  if (setup && !setup.app_unlocked) {
    return (
      <section className="owner-glass-panel rounded-3xl p-4">
        <h2 className="font-semibold">Stock is locked</h2>
        <p className="mt-2 text-sm leading-6 text-zinc-300">
          {recipes?.state === "open"
            ? "Unlocks after you save at least one recipe from the chefs and mark that step done."
            : "Unlocks after your password, PIN, and the chefs' recipes are saved."}
        </p>
        <Link href={recipes?.state === "open" ? "/store/recipes" : "/store/account"} className="mt-4 inline-flex min-h-11 items-center rounded-full bg-white px-4 font-semibold text-black">
          {recipes?.state === "open" ? "Open recipes" : "Open account"}
        </Link>
      </section>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm leading-6 text-zinc-300">
        Quantities only. Prices stay with the owner. You do not type them here.
      </p>
      {error && <p className="text-sm text-red-300">{error}</p>}
      {!setup ? (
        <p className="text-sm text-zinc-400">Loading stock…</p>
      ) : items.length === 0 ? (
        <p className="owner-glass-panel rounded-3xl p-4 text-sm text-zinc-300">
          No items yet. They appear when a recipe names an ingredient or the owner brings in an opening count.
        </p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li key={item.id} className="owner-glass-panel flex items-center justify-between rounded-3xl px-4 py-3">
              <span className="font-medium">{item.item_name}</span>
              <span className="text-sm text-zinc-300">{item.quantity} {item.unit}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
