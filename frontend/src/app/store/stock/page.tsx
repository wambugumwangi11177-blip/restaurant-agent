"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { hasModule, loadSetup, stepById, type SetupPayload } from "@/lib/storeSetup";

type Item = {
  id: number;
  item_name: string;
  quantity: number;
  unit: string;
  buying_unit: string | null;
  units_per_buy: number | null;
  yield_fraction: number;
  zone: string | null;
};
type Zone = { name: string };

export default function StoreStockPage() {
  const [setup, setSetup] = useState<SetupPayload | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [zones, setZones] = useState<Zone[]>([]);
  const [itemName, setItemName] = useState("");
  const [quantity, setQuantity] = useState("");
  const [unit, setUnit] = useState("kg");
  const [zone, setZone] = useState("Main store");
  const [buyingUnit, setBuyingUnit] = useState("");
  const [unitsPerBuy, setUnitsPerBuy] = useState("");
  const [yieldFraction, setYieldFraction] = useState("1");
  const [error, setError] = useState("");

  async function refresh() {
    const next = await loadSetup();
    setSetup(next);
    if (!next.app_unlocked) return;
    const response = await api.get("/api/v1/store/items");
    setItems(response.data.items ?? []);
    setZones(response.data.zones ?? []);
  }

  useEffect(() => {
    refresh().catch(() => setError("Stock could not be loaded."));
  }, []);

  async function saveOpening(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await api.post("/api/v1/store/items/opening", {
        item_name: itemName,
        quantity: Number(quantity),
        unit,
        zone,
        buying_unit: buyingUnit || null,
        units_per_buy: unitsPerBuy ? Number(unitsPerBuy) : null,
        yield_fraction: Number(yieldFraction),
      });
      setItemName("");
      setQuantity("");
      await refresh();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "That count was not saved.");
    }
  }

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
    <div className="space-y-4">
      <p className="text-sm leading-6 text-zinc-300">Quantities only. Prices stay with the owner.</p>
      {setup?.stock_followup && !hasModule(setup, "opening-count") && (
        <section className="owner-glass-panel rounded-3xl p-4">
          <h2 className="font-semibold">Stock count</h2>
          <p className="mt-2 text-sm leading-6 text-zinc-300">{setup.stock_followup.label}</p>
        </section>
      )}
      {hasModule(setup, "opening-count") && (
        <form onSubmit={saveOpening} className="owner-glass-panel space-y-3 rounded-3xl p-4">
          <h2 className="font-semibold">Opening count</h2>
          <label className="block text-sm">Item
            <input required value={itemName} onChange={(event) => setItemName(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">Quantity
              <input required inputMode="decimal" value={quantity} onChange={(event) => setQuantity(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
            </label>
            <label className="block text-sm">Unit
              <input required value={unit} onChange={(event) => setUnit(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
            </label>
          </div>
          <label className="block text-sm">Place
            <select value={zone} onChange={(event) => setZone(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/40 px-3">
              {(zones.length ? zones : [{ name: "Main store" }, { name: "Cold room" }, { name: "Bar" }, { name: "Kitchen" }]).map((entry) => (
                <option key={entry.name}>{entry.name}</option>
              ))}
            </select>
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm">Buying unit
              <input value={buyingUnit} onChange={(event) => setBuyingUnit(event.target.value)} placeholder="crate" className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
            </label>
            <label className="block text-sm">Units inside one
              <input inputMode="decimal" value={unitsPerBuy} onChange={(event) => setUnitsPerBuy(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
            </label>
          </div>
          <label className="block text-sm">Yield (0 to 1)
            <input required inputMode="decimal" value={yieldFraction} onChange={(event) => setYieldFraction(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
          </label>
          {error && <p className="text-sm text-red-300">{error}</p>}
          <button type="submit" className="min-h-11 w-full rounded-full bg-white font-semibold text-black">Save opening count</button>
        </form>
      )}
      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item.id} className="owner-glass-panel rounded-3xl px-4 py-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-medium">{item.item_name}</span>
              <span className="text-zinc-300">{item.quantity} {item.unit}</span>
            </div>
            <p className="mt-1 text-xs text-zinc-500">
              {item.zone || "No place yet"}
              {item.buying_unit ? ` · buys by ${item.buying_unit}${item.units_per_buy ? ` of ${item.units_per_buy}` : ""}` : ""}
              {` · yield ${item.yield_fraction}`}
            </p>
          </li>
        ))}
      </ul>
      <div className="flex gap-3 text-sm text-zinc-400">
        <Link href="/store/issue">Hand to kitchen</Link>
        <Link href="/store/waste">Thrown away</Link>
      </div>
    </div>
  );
}
