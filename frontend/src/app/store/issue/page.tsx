"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import PhotoField from "@/components/store/PhotoField";
import api from "@/lib/api";
import { hasModule, loadSetup, type SetupPayload } from "@/lib/storeSetup";

type Item = { id: number; item_name: string; unit: string };
type Chef = { id: number; name: string };
type Line = { key: number; itemId: string; quantity: string };

function detailOf(err: unknown, fallback: string) {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  return typeof detail === "string" ? detail : fallback;
}

export default function IssuePage() {
  const [setup, setSetup] = useState<SetupPayload | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [chefs, setChefs] = useState<Chef[]>([]);
  const [lines, setLines] = useState<Line[]>([{ key: 1, itemId: "", quantity: "" }]);
  const [chefId, setChefId] = useState("");
  const [pin, setPin] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSetup().then(async (next) => {
      setSetup(next);
      if (!hasModule(next, "store-issue")) return;
      const [itemResponse, chefResponse] = await Promise.all([
        api.get("/api/v1/store/items"),
        api.get("/api/v1/store/chefs"),
      ]);
      setItems(itemResponse.data.items ?? []);
      setChefs(chefResponse.data.chefs ?? []);
    }).catch(() => setError("This page could not be loaded.")).finally(() => setLoading(false));
  }, []);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setSaved("");
    const body = new FormData();
    body.set("lines", JSON.stringify(lines.map((line) => ({
      item_id: Number(line.itemId),
      quantity: Number(line.quantity),
    }))));
    body.set("chef_id", chefId);
    body.set("pin", pin);
    body.set("from_zone", "Main store");
    if (photo) body.set("photo", photo);
    try {
      const response = await api.post("/api/v1/store/handover", body, { headers: { "Content-Type": "multipart/form-data" } });
      const moved = (response.data.lines ?? []).map((line: { quantity: number; unit: string; item_name: string }) => (
        `${line.quantity} ${line.unit} ${line.item_name}`
      )).join(", ");
      setSaved(`${moved} handed to the kitchen. ${response.data.chef_name} confirmed.`);
      setLines([{ key: Date.now(), itemId: "", quantity: "" }]);
      setPin("");
      setPhoto(null);
    } catch (err: unknown) {
      setError(detailOf(err, "That handover was not saved."));
    }
  }

  if (loading) return <p className="text-sm text-zinc-400">Loading the handover…</p>;
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
      <p className="text-sm text-zinc-300">Pick the items and quantities. The chef types their own 4-digit PIN. A photo is optional.</p>
      {items.length === 0 && <p className="text-sm text-zinc-400">Nothing is in the main store yet.</p>}
      {lines.map((line) => (
        <div key={line.key} className="grid grid-cols-[1fr_6rem] gap-2">
          <label className="block text-sm">Item
            <select required value={line.itemId} onChange={(event) => setLines((current) => current.map((entry) => entry.key === line.key ? { ...entry, itemId: event.target.value } : entry))} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/40 px-3">
              <option value="">Choose</option>
              {items.map((item) => <option key={item.id} value={item.id}>{item.item_name}</option>)}
            </select>
          </label>
          <label className="block text-sm">Qty
            <input required inputMode="decimal" value={line.quantity} onChange={(event) => setLines((current) => current.map((entry) => entry.key === line.key ? { ...entry, quantity: event.target.value } : entry))} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
          </label>
        </div>
      ))}
      <button type="button" className="min-h-11 text-sm text-zinc-300" onClick={() => setLines((current) => [...current, { key: Date.now(), itemId: "", quantity: "" }])}>Add another item</button>
      {chefs.length === 0 ? (
        <p className="text-sm text-zinc-300">No chef yet. <Link href="/store/chefs" className="underline">Add a chef</Link> before the handover.</p>
      ) : (
        <label className="block text-sm">Chef
          <select required value={chefId} onChange={(event) => setChefId(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/40 px-3">
            <option value="">Choose</option>
            {chefs.map((chef) => <option key={chef.id} value={chef.id}>{chef.name}</option>)}
          </select>
        </label>
      )}
      <label className="block text-sm">Chef PIN
        <input required inputMode="numeric" autoComplete="off" maxLength={4} value={pin} onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, 4))} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3 tracking-[0.4em]" />
      </label>
      <PhotoField label="Photo of the goods" file={photo} onFile={setPhoto} optional />
      {error && <p className="text-sm text-red-300">{error}</p>}
      {saved && <p className="text-sm text-zinc-200">{saved}</p>}
      <button type="submit" className="min-h-11 w-full rounded-full bg-white font-semibold text-black" disabled={chefs.length === 0}>Hand it over</button>
    </form>
  );
}
