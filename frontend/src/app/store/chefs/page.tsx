"use client";

import { useEffect, useState } from "react";
import PhotoField from "@/components/store/PhotoField";
import api from "@/lib/api";

type Chef = { id: number; name: string; created_by: string | null; created_at: string | null; has_photo: boolean };

function detailOf(err: unknown, fallback: string) {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  return typeof detail === "string" ? detail : fallback;
}

export default function ChefsPage() {
  const [chefs, setChefs] = useState<Chef[] | null>(null);
  const [name, setName] = useState("");
  const [pin, setPin] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");

  async function refresh() {
    const response = await api.get("/api/v1/store/chefs");
    setChefs(response.data.chefs ?? []);
  }

  useEffect(() => {
    refresh().catch(() => setError("Chefs could not be loaded."));
  }, []);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setSaved("");
    const body = new FormData();
    body.set("name", name);
    body.set("pin", pin);
    if (photo) body.set("photo", photo);
    try {
      await api.post("/api/v1/store/chefs", body, { headers: { "Content-Type": "multipart/form-data" } });
      setSaved(`${name} can confirm a handover. They do not get a login.`);
      setName("");
      setPin("");
      setPhoto(null);
      await refresh();
    } catch (err: unknown) {
      setError(detailOf(err, "That chef was not saved."));
    }
  }

  return (
    <div className="space-y-4">
      <form onSubmit={save} className="owner-glass-panel space-y-3 rounded-3xl p-4">
        <p className="text-sm text-zinc-300">Add a chef with a name and a 4-digit PIN. A photo is optional. Chefs do not sign in.</p>
        <label className="block text-sm">Name
          <input required value={name} onChange={(event) => setName(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
        </label>
        <label className="block text-sm">PIN
          <input required inputMode="numeric" autoComplete="off" maxLength={4} value={pin} onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, 4))} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3 tracking-[0.4em]" />
        </label>
        <PhotoField label="Photo" file={photo} onFile={setPhoto} optional />
        {error && <p className="text-sm text-red-300">{error}</p>}
        {saved && <p className="text-sm text-zinc-200">{saved}</p>}
        <button type="submit" className="min-h-11 w-full rounded-full bg-white font-semibold text-black">Add chef</button>
      </form>
      {chefs === null ? (
        <p className="text-sm text-zinc-400">Loading chefs…</p>
      ) : chefs.length === 0 ? (
        <p className="owner-glass-panel rounded-3xl p-4 text-sm text-zinc-300">No chef yet.</p>
      ) : (
        <ul className="space-y-2">
          {chefs.map((chef) => (
            <li key={chef.id} className="owner-glass-panel rounded-3xl px-4 py-3 text-sm">
              <p className="font-medium">{chef.name}</p>
              <p className="mt-1 text-xs text-zinc-500">{chef.created_by} · {chef.created_at}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
