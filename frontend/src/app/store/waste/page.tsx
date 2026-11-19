"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import PhotoField from "@/components/store/PhotoField";
import api from "@/lib/api";
import { hasModule, loadSetup, type SetupPayload } from "@/lib/storeSetup";

type Item = { id: number; item_name: string; unit: string };
type Chef = { id: number; name: string };

const REASONS = [
  ["spoiled", "Spoiled"],
  ["broken", "Broken"],
  ["expired", "Expired"],
  ["spilled", "Spilled"],
  ["other", "Other"],
] as const;

function detailOf(err: unknown, fallback: string) {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  return typeof detail === "string" ? detail : fallback;
}

export default function WastePage() {
  const [setup, setSetup] = useState<SetupPayload | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [chefs, setChefs] = useState<Chef[]>([]);
  const [itemId, setItemId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState("spoiled");
  const [note, setNote] = useState("");
  const [chefId, setChefId] = useState("");
  const [pin, setPin] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSetup().then(async (next) => {
      setSetup(next);
      if (!hasModule(next, "waste")) return;
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
    if (!photo) {
      setError("Add a photo of what was thrown away.");
      return;
    }
    const body = new FormData();
    body.set("item_id", itemId);
    body.set("quantity", quantity);
    body.set("zone", "Main store");
    body.set("reason_code", reason);
    body.set("reason_text", note);
    body.set("chef_id", chefId);
    body.set("pin", pin);
    body.set("photo", photo);
    try {
      const response = await api.post("/api/v1/store/spoilage", body, { headers: { "Content-Type": "multipart/form-data" } });
      setSaved(response.data.status === "needs_approval"
        ? `${response.data.quantity} ${response.data.unit} written off. The owner will look at this.`
        : `${response.data.quantity} ${response.data.unit} written off.`);
      setQuantity("");
      setNote("");
      setPin("");
      setPhoto(null);
    } catch (err: unknown) {
      setError(detailOf(err, "That waste line was not saved."));
    }
  }

  if (loading) return <p className="text-sm text-zinc-400">Loading waste…</p>;
  if (setup && !hasModule(setup, "waste")) {
    return (
      <section className="owner-glass-panel rounded-3xl p-4">
        <h2 className="font-semibold">Waste is locked</h2>
        <Link href="/store/questions" className="mt-4 inline-flex min-h-11 items-center rounded-full bg-white px-4 font-semibold text-black">Open questions</Link>
      </section>
    );
  }

  return (
    <form onSubmit={save} className="owner-glass-panel space-y-3 rounded-3xl p-4">
      <p className="text-sm text-zinc-300">Say why it was thrown away, add a photo, and have a second person confirm with their PIN.</p>
      {items.length === 0 && <p className="text-sm text-zinc-400">Nothing is in stock to write off.</p>}
      <label className="block text-sm">Item
        <select required value={itemId} onChange={(event) => setItemId(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/40 px-3">
          <option value="">Choose</option>
          {items.map((item) => <option key={item.id} value={item.id}>{item.item_name}</option>)}
        </select>
      </label>
      <label className="block text-sm">Quantity
        <input required inputMode="decimal" value={quantity} onChange={(event) => setQuantity(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
      </label>
      <label className="block text-sm">Reason
        <select value={reason} onChange={(event) => setReason(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/40 px-3">
          {REASONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label className="block text-sm">What happened
        <input value={note} onChange={(event) => setNote(event.target.value)} required={reason === "other"} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
      </label>
      <PhotoField label="Photo" file={photo} onFile={setPhoto} />
      {chefs.length === 0 ? (
        <p className="text-sm text-zinc-300">No chef yet. <Link href="/store/chefs" className="underline">Add a chef</Link> so someone else can confirm.</p>
      ) : (
        <label className="block text-sm">Second person
          <select required value={chefId} onChange={(event) => setChefId(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/40 px-3">
            <option value="">Choose</option>
            {chefs.map((chef) => <option key={chef.id} value={chef.id}>{chef.name}</option>)}
          </select>
        </label>
      )}
      <label className="block text-sm">Their PIN
        <input required inputMode="numeric" autoComplete="off" maxLength={4} value={pin} onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, 4))} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3 tracking-[0.4em]" />
      </label>
      {error && <p className="text-sm text-red-300">{error}</p>}
      {saved && <p className="text-sm text-zinc-200">{saved}</p>}
      <button type="submit" className="min-h-11 w-full rounded-full bg-white font-semibold text-black" disabled={chefs.length === 0}>Save waste</button>
    </form>
  );
}
