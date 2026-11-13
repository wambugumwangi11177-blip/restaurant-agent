"use client";

import { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";

export type FeedEvent = {
  kind: string;
  id: number;
  headline?: string;
  person_name?: string;
  person_email?: string;
  initial?: string;
  created_at?: string | null;
  status?: string;
  working_alone?: boolean;
  photo_path?: string | null;
  owner_note?: string;
  amount_cents?: number | null;
  ai?: { label?: string; status?: string; note?: string | null } | null;
};

export type FeedPayload = {
  pending: FeedEvent[];
  events: FeedEvent[];
  attention?: { count: number; sentence: string };
  cards?: { id: string; title: string; sentence: string }[];
  unknown_costs?: string[];
  recipes_missing?: number;
  approved_bills?: string[];
  till_live?: boolean;
};

const TYPES = ["delivery", "handover", "waste", "close", "cost", "setup"];

function dayLabel(iso?: string | null) {
  if (!iso) return "Earlier";
  return new Date(iso).toLocaleDateString("en-KE", { weekday: "long", day: "numeric", month: "long" });
}

function clock(iso?: string | null) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("en-KE", { hour: "2-digit", minute: "2-digit" });
}

function Icon({ kind }: { kind: string }) {
  const label = kind === "waste" ? "Waste" : kind;
  return (
    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl border border-white/15 text-[10px] uppercase tracking-wide text-zinc-300" aria-hidden>
      {label.slice(0, 1)}
    </span>
  );
}

export function useOwnerFeed() {
  const [data, setData] = useState<FeedPayload | null>(null);
  const [error, setError] = useState("");

  async function refresh() {
    const response = await api.get("/api/v1/store/approvals");
    setData(response.data);
  }

  useEffect(() => {
    refresh().catch(() => setError("The feed could not be loaded."));
  }, []);

  return { data, error, refresh, setError };
}

export default function OwnerFeed({
  data,
  onChanged,
}: {
  data: FeedPayload;
  onChanged: () => Promise<void>;
}) {
  const [person, setPerson] = useState("all");
  const [kind, setKind] = useState("all");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [photo, setPhoto] = useState<string | null>(null);
  const [thumbs, setThumbs] = useState<Record<string, string>>({});

  const people = useMemo(() => {
    const names = new Set<string>();
    for (const event of data.events) if (event.person_name) names.add(event.person_name);
    return [...names];
  }, [data.events]);

  const visible = data.events.filter((event) => {
    if (person !== "all" && event.person_name !== person) return false;
    if (kind !== "all" && event.kind !== kind) return false;
    return true;
  });

  const groups: { day: string; items: FeedEvent[] }[] = [];
  for (const event of visible) {
    const day = dayLabel(event.created_at);
    const last = groups[groups.length - 1];
    if (!last || last.day !== day) groups.push({ day, items: [event] });
    else last.items.push(event);
  }

  async function openPhoto(path: string) {
    if (thumbs[path]) {
      setPhoto(thumbs[path]);
      return;
    }
    const response = await api.get(path, { responseType: "blob" });
    const url = URL.createObjectURL(response.data);
    setThumbs((current) => ({ ...current, [path]: url }));
    setPhoto(url);
  }

  async function decide(event: FeedEvent, decision: "approve" | "decline") {
    setBusy(`${event.kind}-${event.id}`);
    setError("");
    try {
      await api.post("/api/v1/store/approvals", {
        kind: event.kind === "waste" ? "waste" : event.kind,
        id: event.id,
        decision,
        note,
      });
      setNote("");
      await onChanged();
    } catch {
      setError("That decision was not saved.");
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <select aria-label="Person" value={person} onChange={(event) => setPerson(event.target.value)} className="min-h-11 flex-1 rounded-full border border-white/15 bg-black/40 px-3 text-sm">
          <option value="all">Everyone</option>
          {people.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>
        <select aria-label="Type" value={kind} onChange={(event) => setKind(event.target.value)} className="min-h-11 flex-1 rounded-full border border-white/15 bg-black/40 px-3 text-sm">
          <option value="all">All types</option>
          {TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
        </select>
      </div>
      {data.pending.length > 0 && (
        <section className="space-y-2">
          {data.pending.map((event) => (
            <article key={`wait-${event.kind}-${event.id}`} className="owner-glass-panel rounded-3xl p-4">
              <p className="text-xs uppercase tracking-[0.14em] text-zinc-400">Needs you</p>
              <p className="mt-1 font-semibold">{event.headline}</p>
              {event.amount_cents != null && <p className="mt-1 text-sm text-zinc-300">{(event.amount_cents / 100).toLocaleString("en-KE")} KES</p>}
              <label className="mt-3 block text-sm">Note, if you want one
                <input value={note} onChange={(event) => setNote(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
              </label>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <button type="button" disabled={busy === `${event.kind}-${event.id}`} onClick={() => decide(event, "approve")} className="min-h-11 rounded-full bg-white font-semibold text-black">Approve</button>
                <button type="button" disabled={busy === `${event.kind}-${event.id}`} onClick={() => decide(event, "decline")} className="min-h-11 rounded-full border border-white/20">Decline</button>
              </div>
            </article>
          ))}
        </section>
      )}
      {groups.length === 0 && <p className="owner-glass-panel rounded-3xl p-4 text-sm text-zinc-300">Nothing has been recorded yet.</p>}
      {groups.map((group) => (
        <section key={group.day}>
          <h2 className="mb-2 text-xs font-bold uppercase tracking-[0.14em] text-zinc-500">{group.day}</h2>
          <ul className="space-y-2">
            {group.items.map((event) => (
              <li key={`${event.kind}-${event.id}`} className="owner-glass-panel rounded-3xl p-4">
                <div className="flex gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-full bg-white text-sm font-semibold text-black">{event.initial || "?"}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-semibold">{event.person_name || "Someone"}</p>
                      <time className="text-xs text-zinc-500">{clock(event.created_at)}</time>
                    </div>
                    {event.person_email && <p className="text-[11px] text-zinc-500">{event.person_email}</p>}
                    <div className="mt-2 flex gap-2">
                      <Icon kind={event.kind} />
                      <p className="text-sm leading-6 text-zinc-100">{event.headline}</p>
                    </div>
                    {event.working_alone && <p className="mt-2 text-xs uppercase tracking-wide text-amber-200">Working alone</p>}
                    {event.ai?.label && (
                      <p className="mt-2 inline-flex rounded-full border border-white/20 px-2 py-1 text-[11px] text-zinc-300">
                        AI · {event.ai.note || event.ai.status}
                      </p>
                    )}
                    {event.photo_path && (
                      <button type="button" className="mt-2 block" onClick={() => openPhoto(event.photo_path!)}>
                        {thumbs[event.photo_path] ? (
                          <img src={thumbs[event.photo_path]} alt="" className="h-16 w-16 rounded-2xl object-cover" />
                        ) : (
                          <span className="inline-flex min-h-11 items-center text-sm underline">Open photo</span>
                        )}
                      </button>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}
      {error && <p className="text-sm text-red-300">{error}</p>}
      {photo && (
        <button type="button" className="fixed inset-0 z-[80] flex items-center justify-center bg-black/80 p-4" onClick={() => setPhoto(null)}>
          <img src={photo} alt="Full size" className="max-h-full max-w-full rounded-2xl" />
        </button>
      )}
    </div>
  );
}
