"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { hasModule, loadSetup, type SetupPayload } from "@/lib/storeSetup";

type Item = { id: number; item_name: string; unit: string };

export default function IssuePage() {
  const [setup, setSetup] = useState<SetupPayload | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [itemId, setItemId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");

  useEffect(() => {
    loadSetup().then(async (next) => {
      setSetup(next);
      if (!hasModule(next, "store-issue")) return;
      const response = await api.get("/api/v1/store/items");
      setItems(response.data.items ?? []);
    }).catch(() => setError("This page could not be loaded."));
  }, []);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const response = await api.post("/api/v1/store/issue", {
        item_id: Number(itemId),
        quantity: Number(quantity),
        from_zone: "Main store",
        to_zone: "Kitchen",
      });
      setSaved(`${response.data.quantity} ${response.data.unit} handed to the kitchen.`);
      setQuantity("");
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "That issue was not saved.");
    }
  }

  if (setup && !hasModule(setup, "store-issue")) {
    return (
      <section className="owner-glass-panel rounded-3xl p-4">
        <h2 className="font-semibold">Handing stock to the kitchen is locked</h2>
        <Link href="/store/questions" className="mt-4 inline-flex min-h-11 items-center rounded-full bg-white px-4 font-semibold text-black">Open questions</Link>
      </section>
    );
  }

  return (
    <form onSubmit={save} className="owner-glass-panel space-y-3 rounded-3xl p-4">
      <p className="text-sm text-zinc-300">Move a quantity from the main store to the kitchen. The total in the restaurant does not change.</p>
      <label className="block text-sm">Item
        <select required value={itemId} onChange={(event) => setItemId(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/40 px-3">
          <option value="">Choose</option>
          {items.map((item) => <option key={item.id} value={item.id}>{item.item_name}</option>)}
        </select>
      </label>
      <label className="block text-sm">Quantity
        <input required inputMode="decimal" value={quantity} onChange={(event) => setQuantity(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
      </label>
      {error && <p className="text-sm text-red-300">{error}</p>}
      {saved && <p className="text-sm text-zinc-200">{saved}</p>}
      <button type="submit" className="min-h-11 w-full rounded-full bg-white font-semibold text-black">Hand it over</button>
    </form>
  );
}
