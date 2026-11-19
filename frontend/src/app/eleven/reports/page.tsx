"use client";

import { useMemo, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import { dayLabel, useOwnerFeed, type FeedEvent } from "@/components/eleven/OwnerFeed";

const BUCKETS = [
  { id: "delivery", label: "Deliveries" },
  { id: "handover", label: "Kitchen handovers" },
  { id: "waste", label: "Waste" },
  { id: "close", label: "Day closes" },
  { id: "cost", label: "Bills" },
  { id: "zone_photo", label: "Zone photos" },
] as const;

function countByKind(events: FeedEvent[], sinceMs: number) {
  const counts: Record<string, number> = {};
  for (const { id } of BUCKETS) counts[id] = 0;
  for (const event of events) {
    if (!event.created_at) continue;
    const t = new Date(event.created_at).getTime();
    if (Number.isNaN(t) || t < sinceMs) continue;
    if (counts[event.kind] != null) counts[event.kind] += 1;
  }
  return counts;
}

export default function ElevenReportsPage() {
  const { data, error } = useOwnerFeed();
  const zone = data?.timezone;
  const [now] = useState(() => Date.now());
  const dayStart = now - 86_400_000;
  const weekStart = now - 7 * 86_400_000;

  const today = useMemo(
    () => (data ? countByKind(data.events, dayStart) : null),
    [data, dayStart],
  );
  const week = useMemo(
    () => (data ? countByKind(data.events, weekStart) : null),
    [data, weekStart],
  );

  const recentDays = useMemo(() => {
    if (!data) return [];
    const map = new Map<string, FeedEvent[]>();
    for (const event of data.events) {
      const label = dayLabel(event.created_at, zone);
      const list = map.get(label) ?? [];
      list.push(event);
      map.set(label, list);
    }
    return [...map.entries()].slice(0, 7);
  }, [data, zone]);

  return (
    <OwnerShell title="Reports">
      <p className="mb-4 text-xs text-zinc-400">Summaries from store deliveries, handovers, waste, closes, bills, and zone photos.</p>
      {error && <p className="text-sm text-red-300">{error}</p>}
      {!data && !error && <p className="text-sm text-zinc-400">Loading…</p>}
      {data && (
        <div className="space-y-6">
          <section className="owner-glass-panel rounded-2xl p-4">
            <h2 className="owner-label">Today</h2>
            <ul className="mt-2 space-y-1 text-sm">
              {BUCKETS.map(({ id, label }) => (
                <li key={id} className="flex justify-between gap-3">
                  <span>{label}</span>
                  <span className="font-semibold">{today?.[id] ?? 0}</span>
                </li>
              ))}
            </ul>
          </section>
          <section className="owner-glass-panel rounded-2xl p-4">
            <h2 className="owner-label">Past 7 days</h2>
            <ul className="mt-2 space-y-1 text-sm">
              {BUCKETS.map(({ id, label }) => (
                <li key={id} className="flex justify-between gap-3">
                  <span>{label}</span>
                  <span className="font-semibold">{week?.[id] ?? 0}</span>
                </li>
              ))}
            </ul>
          </section>
          <section>
            <h2 className="owner-label">Recent days</h2>
            <ul className="mt-2 space-y-3">
              {recentDays.length === 0 && <li className="text-sm text-zinc-400">Nothing recorded yet.</li>}
              {recentDays.map(([day, items]) => (
                <li key={day} className="owner-glass-panel rounded-2xl p-4">
                  <p className="font-semibold">{day}</p>
                  <p className="mt-1 text-sm text-zinc-400">{items.length} event{items.length === 1 ? "" : "s"}</p>
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </OwnerShell>
  );
}