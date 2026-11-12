"use client";

import { useEffect, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import api from "@/lib/api";

type Line = {
  item_name: string;
  unit: string;
  quantity?: number;
  expected_qty?: number;
  counted_qty?: number;
  difference?: number;
};
type Event = {
  kind: "spoilage" | "close" | "handover";
  id: number;
  status?: string;
  created_by?: string | null;
  created_at?: string | null;
  working_alone?: boolean;
  item_name?: string;
  quantity?: number;
  unit?: string;
  reason_code?: string;
  reason_text?: string;
  chef_name?: string | null;
  lines?: Line[];
  ai?: { label?: string; status?: string; note?: string | null } | null;
};

function textFor(event: Event) {
  if (event.kind === "spoilage") {
    return `${event.quantity} ${event.unit} of ${event.item_name} · ${event.reason_code}${event.reason_text ? ` · ${event.reason_text}` : ""}`;
  }
  if (event.kind === "handover") {
    const lines = (event.lines ?? []).map((line) => `${line.item_name} ${line.quantity ?? ""} ${line.unit}`).join(", ");
    return lines || "Handover";
  }
  const diffs = (event.lines ?? []).filter((line) => (line.difference ?? 0) !== 0);
  if (diffs.length === 0) return "The count matches the books.";
  return diffs.map((line) => `${line.item_name}: books ${line.expected_qty}, counted ${line.counted_qty}`).join(" · ");
}

export default function ApprovalsPage() {
  const [pending, setPending] = useState<Event[] | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string>("");

  async function refresh() {
    const response = await api.get("/api/v1/store/approvals");
    setPending(response.data.pending ?? []);
    setEvents(response.data.events ?? []);
  }

  useEffect(() => {
    refresh().catch(() => setError("Approvals could not be loaded."));
  }, []);

  async function approve(event: Event) {
    setError("");
    setBusy(`${event.kind}-${event.id}`);
    try {
      await api.post("/api/v1/store/approvals", { kind: event.kind, id: event.id });
      await refresh();
    } catch {
      setError("That approval was not saved.");
    } finally {
      setBusy("");
    }
  }

  return (
    <OwnerShell title="Approvals">
      <div className="space-y-4">
        <section className="space-y-2">
          <h2 className="text-sm font-semibold">Waiting</h2>
          {pending === null && <p className="text-sm text-zinc-400">Loading…</p>}
          {pending?.length === 0 && <p className="owner-glass-panel rounded-3xl p-4 text-sm text-zinc-300">Nothing is waiting.</p>}
          {pending?.map((event) => (
            <article key={`${event.kind}-${event.id}`} className="owner-glass-panel rounded-3xl p-4 text-sm">
              <p className="font-medium capitalize">{event.kind}</p>
              {event.working_alone && <p className="mt-1 text-xs uppercase tracking-wide text-amber-200">Working alone</p>}
              <p className="mt-2 text-zinc-200">{textFor(event)}</p>
              <p className="mt-1 text-xs text-zinc-500">{event.created_by} · {event.created_at}</p>
              <button type="button" disabled={busy === `${event.kind}-${event.id}`} onClick={() => approve(event)} className="mt-3 min-h-11 rounded-full bg-white px-4 font-semibold text-black">
                Approve
              </button>
            </article>
          ))}
        </section>
        <section className="space-y-2">
          <h2 className="text-sm font-semibold">Store activity</h2>
          {events.length === 0 && pending !== null && <p className="owner-glass-panel rounded-3xl p-4 text-sm text-zinc-300">Nothing has been recorded yet.</p>}
          {events.map((event) => (
            <article key={`feed-${event.kind}-${event.id}`} className="owner-glass-panel rounded-3xl p-4 text-sm">
              <div className="flex items-center justify-between gap-3">
                <p className="font-medium capitalize">{event.kind}</p>
                {event.working_alone && <span className="rounded-full border border-amber-200/40 px-2 py-0.5 text-[10px] uppercase tracking-wide text-amber-100">Working alone</span>}
              </div>
              <p className="mt-2 text-zinc-200">{textFor(event)}</p>
              {event.ai?.label && (
                <p className="mt-2 text-xs text-zinc-400">AI · {event.ai.status}{event.ai.note ? ` · ${event.ai.note}` : ""}</p>
              )}
              <p className="mt-1 text-xs text-zinc-500">{event.created_by} · {event.created_at}{event.status ? ` · ${event.status}` : ""}</p>
            </article>
          ))}
        </section>
        {error && <p className="text-sm text-red-300">{error}</p>}
      </div>
    </OwnerShell>
  );
}
