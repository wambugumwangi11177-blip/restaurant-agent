"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { hasModule, loadSetup, type SetupPayload } from "@/lib/storeSetup";

type Expected = { item_id: number; item_name: string; unit: string; expected_qty: number };

function detailOf(err: unknown, fallback: string) {
  const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  return typeof detail === "string" ? detail : fallback;
}

export default function ClosePage() {
  const [setup, setSetup] = useState<SetupPayload | null>(null);
  const [items, setItems] = useState<Expected[]>([]);
  const [counts, setCounts] = useState<Record<number, string>>({});
  const [alone, setAlone] = useState(false);
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSetup().then(async (next) => {
      setSetup(next);
      if (!hasModule(next, "day-close")) return;
      const expected = await api.get("/api/v1/store/close/expected");
      setItems(expected.data.items ?? []);
    }).catch(() => setError("The count could not be loaded.")).finally(() => setLoading(false));
  }, []);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setSaved("");
    try {
      const response = await api.post("/api/v1/store/close", {
        working_alone: alone,
        pin: alone ? "" : pin,
        lines: items.map((item) => ({ item_id: item.item_id, counted_qty: Number(counts[item.item_id]) })),
      });
      setSaved(response.data.message === "Saved."
        ? (alone ? "Saved. This close is marked working alone." : "Saved.")
        : "Saved. The owner will look at the difference.");
      setPin("");
    } catch (err: unknown) {
      setError(detailOf(err, "The close was not saved."));
    }
  }

  if (loading) return <p className="text-sm text-zinc-400">Loading the count…</p>;
  if (setup && !hasModule(setup, "day-close")) {
    return (
      <section className="owner-glass-panel rounded-3xl p-4">
        <h2 className="font-semibold">The day close is locked</h2>
        <p className="mt-2 text-sm text-zinc-300">It opens when the questions say you close the day.</p>
        <Link href="/store/questions" className="mt-4 inline-flex min-h-11 items-center rounded-full bg-white px-4 font-semibold text-black">Open questions</Link>
      </section>
    );
  }

  return (
    <form onSubmit={save} className="owner-glass-panel space-y-3 rounded-3xl p-4">
      <p className="text-sm text-zinc-300">Count what is actually there. The other manager types their PIN, or mark that you are working alone. A chef does not close the day.</p>
      {items.length === 0 ? (
        <p className="text-sm text-zinc-400">Nothing is in stock to count.</p>
      ) : (
        <ul className="space-y-3">
          {items.map((item) => (
            <li key={item.item_id}>
              <label className="block text-sm">{item.item_name}
                <span className="mt-1 block text-xs text-zinc-500">On the books: {item.expected_qty} {item.unit}</span>
                <input required inputMode="decimal" value={counts[item.item_id] ?? ""} onChange={(event) => setCounts((current) => ({ ...current, [item.item_id]: event.target.value }))} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
              </label>
            </li>
          ))}
        </ul>
      )}
      <label className="flex min-h-11 items-center gap-3 text-sm">
        <input type="checkbox" checked={alone} onChange={(event) => setAlone(event.target.checked)} />
        I am working alone
      </label>
      {!alone && (
        <label className="block text-sm">The other manager&apos;s PIN
          <input required inputMode="numeric" autoComplete="off" maxLength={4} value={pin} onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, 4))} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3 tracking-[0.4em]" />
        </label>
      )}
      {error && <p className="text-sm text-red-300">{error}</p>}
      {saved && <p className="text-sm text-zinc-200">{saved}</p>}
      <button type="submit" className="min-h-11 w-full rounded-full bg-white font-semibold text-black">Close the day</button>
    </form>
  );
}
