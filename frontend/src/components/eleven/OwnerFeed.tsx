"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowRightLeft, ClipboardCheck, Receipt, Settings2, Trash2, Truck } from "lucide-react";
import api from "@/lib/api";

export type FeedEvent = {
  kind: string;
  id: number;
  headline?: string;
  emphasis?: string | null;
  action?: string;
  person_name?: string;
  person_email?: string;
  initial?: string;
  created_at?: string | null;
  status?: string;
  working_alone?: boolean;
  photo_path?: string | null;
  owner_note?: string;
  amount_cents?: number | null;
  label?: string;
  item_name?: string;
  quantity?: number;
  unit?: string;
  ai?: { label?: string; status?: string; note?: string | null } | null;
};

export type FeedCard = {
  id: string;
  title: string;
  sentence: string;
  figure?: string | null;
  quiet?: boolean;
};

export type FeedPayload = {
  pending: FeedEvent[];
  events: FeedEvent[];
  timezone?: string;
  attention?: { count: number; sentence: string };
  cards?: FeedCard[];
  unknown_costs?: string[];
  recipes_missing?: number;
  approved_bills?: string[];
  till_live?: boolean;
};

const TYPES = [
  { id: "delivery", label: "Delivery" },
  { id: "handover", label: "Handover" },
  { id: "waste", label: "Waste" },
  { id: "close", label: "Close" },
  { id: "cost", label: "Bills" },
];

const ICONS = {
  delivery: Truck,
  handover: ArrowRightLeft,
  waste: Trash2,
  close: ClipboardCheck,
  cost: Receipt,
  setup: Settings2,
} as const;

function zoneOf(zone?: string) {
  return zone || "Africa/Nairobi";
}

function instant(iso?: string | null) {
  if (!iso) return null;
  const stamped = /Z$|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`;
  const date = new Date(stamped);
  return Number.isNaN(date.getTime()) ? null : date;
}

function dayKey(date: Date, zone: string) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
}

export function dayLabel(iso: string | null | undefined, zone?: string) {
  const date = instant(iso);
  const tz = zoneOf(zone);
  if (!date) return "Earlier";
  const key = dayKey(date, tz);
  const today = dayKey(new Date(), tz);
  const yesterday = dayKey(new Date(Date.now() - 86_400_000), tz);
  if (key === today) return "Today";
  if (key === yesterday) return "Yesterday";
  return date.toLocaleDateString("en-KE", { timeZone: tz, weekday: "long", day: "numeric", month: "long" });
}

export function clockLabel(iso: string | null | undefined, zone?: string) {
  const date = instant(iso);
  if (!date) return "";
  return date
    .toLocaleTimeString("en-US", { timeZone: zoneOf(zone), hour: "numeric", minute: "2-digit", hour12: true })
    .replace(" AM", " am")
    .replace(" PM", " pm");
}

function withoutActor(text: string, name?: string) {
  const trimmed = name && text.startsWith(`${name} `) ? text.slice(name.length + 1) : text;
  return trimmed ? trimmed.charAt(0).toUpperCase() + trimmed.slice(1) : trimmed;
}

function Headline({ text, emphasis, name }: { text?: string; emphasis?: string | null; name?: string }) {
  const line = text ? withoutActor(text, name) : "";
  if (!line) return null;
  if (!emphasis || !line.includes(emphasis)) return <>{line}</>;
  const at = line.indexOf(emphasis);
  return (
    <>
      {line.slice(0, at)}
      <strong className="font-semibold text-white">{emphasis}</strong>
      {line.slice(at + emphasis.length)}
    </>
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
  mode = "feed",
}: {
  data: FeedPayload;
  onChanged: () => Promise<void>;
  mode?: "feed" | "approvals";
}) {
  const [person, setPerson] = useState("all");
  const [kind, setKind] = useState("all");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [photo, setPhoto] = useState<string | null>(null);
  const [thumbs, setThumbs] = useState<Record<string, string>>({});
  const [who, setWho] = useState<FeedEvent | null>(null);
  const zone = data.timezone;

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

  const photoKey = visible.map((event) => event.photo_path || "").join("|");

  useEffect(() => {
    let cancel = false;
    const paths = photoKey.split("|").filter(Boolean);
    for (const path of paths) {
      api.get(path, { responseType: "blob" }).then((response) => {
        if (cancel) return;
        const url = URL.createObjectURL(response.data);
        setThumbs((current) => (current[path] ? current : { ...current, [path]: url }));
      }).catch(() => undefined);
    }
    return () => {
      cancel = true;
    };
  }, [photoKey]);

  const groups: { day: string; items: FeedEvent[] }[] = [];
  for (const event of visible) {
    const day = dayLabel(event.created_at, zone);
    const last = groups[groups.length - 1];
    if (!last || last.day !== day) groups.push({ day, items: [event] });
    else last.items.push(event);
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

  const done = data.events.filter((event) => event.status === "approved" || event.status === "declined");

  return (
    <div className="space-y-4">
      {mode === "feed" && (
        <>
          <div className="flex flex-wrap gap-2">
            <button type="button" className={`owner-chip ${person === "all" ? "is-on" : ""}`} onClick={() => setPerson("all")}>Everyone</button>
            {people.map((name) => (
              <button key={name} type="button" className={`owner-chip ${person === name ? "is-on" : ""}`} onClick={() => setPerson(name)}>{name}</button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className={`owner-chip ${kind === "all" ? "is-on" : ""}`} onClick={() => setKind("all")}>All types</button>
            {TYPES.map((type) => (
              <button key={type.id} type="button" className={`owner-chip ${kind === type.id ? "is-on" : ""}`} onClick={() => setKind(type.id)}>{type.label}</button>
            ))}
          </div>
        </>
      )}

      {mode === "approvals" && (
        <>
          <h2 className="owner-label">Needs you</h2>
          {data.pending.length === 0 ? (
            <p className="owner-quiet">Nothing needs you.</p>
          ) : (
            <ul className="space-y-3">
              {data.pending.map((event) => (
                <li key={`wait-${event.kind}-${event.id}`} id={`${event.kind}-${event.id}`} className="owner-glass-panel rounded-2xl p-4">
                  <p className="text-[0.9375rem] font-medium leading-6">{event.action || event.headline}</p>
                  {event.amount_cents != null && (
                    <p className="owner-figure">{(event.amount_cents / 100).toLocaleString("en-KE")} KES</p>
                  )}
                  <label className="mt-3 block text-sm text-zinc-300">
                    Note, if you want one
                    <input value={note} onChange={(event) => setNote(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
                  </label>
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    <button type="button" disabled={busy === `${event.kind}-${event.id}`} onClick={() => decide(event, "approve")} className="min-h-11 rounded-full bg-white font-semibold text-black">Approve</button>
                    <button type="button" disabled={busy === `${event.kind}-${event.id}`} onClick={() => decide(event, "decline")} className="min-h-11 rounded-full border border-white/20">Decline</button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <h2 className="owner-label">Done</h2>
          {done.length === 0 ? (
            <p className="owner-quiet">Nothing has been decided yet.</p>
          ) : (
            <ul className="owner-glass-panel divide-y divide-white/10 rounded-2xl px-4">
              {done.map((event) => (
                <li key={`done-${event.kind}-${event.id}`} className="flex items-baseline justify-between gap-3 py-3 text-[0.9375rem]">
                  <span>{event.headline}</span>
                  <span className="shrink-0 text-xs uppercase tracking-wide text-zinc-500">{event.status}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {mode === "feed" && groups.length === 0 && <p className="owner-quiet">Nothing has been recorded yet.</p>}
      {mode === "feed" && groups.map((group) => (
        <section key={group.day}>
          <h2 className="owner-label">{group.day}</h2>
          <ul className="owner-glass-panel divide-y divide-white/10 rounded-2xl px-3">
            {group.items.map((event) => {
              const Icon = ICONS[event.kind as keyof typeof ICONS] ?? Settings2;
              return (
                <li key={`${event.kind}-${event.id}`} className="flex items-center gap-3 py-3">
                  <Icon size={20} strokeWidth={1.75} className="shrink-0 text-zinc-300" aria-hidden />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <p className="line-clamp-2 text-[0.9375rem] leading-5 text-zinc-100">
                        <Headline text={event.headline} emphasis={event.emphasis} name={event.person_name} />
                      </p>
                      <time className="shrink-0 text-xs text-zinc-400">{clockLabel(event.created_at, zone)}</time>
                    </div>
                    <button type="button" className="mt-1 flex items-center gap-2 text-left" onClick={() => setWho(event)}>
                      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-white text-[10px] font-semibold text-black">{event.initial || "?"}</span>
                      <span className="text-sm text-zinc-300">{event.person_name || "Someone"}</span>
                    </button>
                    {event.working_alone && <p className="mt-1 text-[11px] uppercase tracking-wide text-zinc-400">Working alone</p>}
                    {event.ai?.note && (
                      <p className="mt-1 inline-flex rounded-full border border-white/20 px-2 py-0.5 text-[11px] text-zinc-300">AI · {event.ai.note}</p>
                    )}
                  </div>
                  {event.photo_path && (
                    <button
                      type="button"
                      className="shrink-0"
                      aria-label="Open photo"
                      onClick={() => {
                        const path = event.photo_path!;
                        if (thumbs[path]) {
                          setPhoto(thumbs[path]);
                          return;
                        }
                        api.get(path, { responseType: "blob" }).then((response) => {
                          const url = URL.createObjectURL(response.data);
                          setThumbs((current) => ({ ...current, [path]: url }));
                          setPhoto(url);
                        }).catch(() => undefined);
                      }}
                    >
                      {thumbs[event.photo_path] ? (
                        <img src={thumbs[event.photo_path]} alt="" className="h-12 w-12 rounded-xl object-cover" />
                      ) : (
                        <span className="block h-12 w-12 rounded-xl bg-white/10" />
                      )}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ))}

      {error && <p className="text-sm text-red-300">{error}</p>}
      {photo && (
        <button type="button" className="fixed inset-0 z-[80] flex items-center justify-center bg-black/90 p-4" onClick={() => setPhoto(null)}>
          <img src={photo} alt="Full size" className="max-h-full max-w-full" />
        </button>
      )}
      {who && (
        <button type="button" className="fixed inset-0 z-[70] flex items-end justify-center bg-black/60 p-4" onClick={() => setWho(null)}>
          <div className="owner-glass-panel w-full max-w-md rounded-2xl p-4 text-left" onClick={(event) => event.stopPropagation()} role="dialog" aria-label="Who did this">
            <p className="text-lg font-semibold">{who.person_name || "Someone"}</p>
            <p className="mt-1 text-sm text-zinc-400">{who.person_email || "No email on file."}</p>
            <button type="button" className="mt-4 min-h-11 w-full rounded-full bg-white font-semibold text-black" onClick={() => setWho(null)}>Close</button>
          </div>
        </button>
      )}
    </div>
  );
}
