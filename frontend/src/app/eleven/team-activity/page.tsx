"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import api from "@/lib/api";
import { getErrorMessage } from "@/lib/errors";

type Photo = { label: string; path: string };
type Line = { item: string; quantity: number; unit: string };
type Stamp = { id: number; at: string; day: string; time: string; person_id: number; person_name: string };
type TeamEvent = Stamp & {
  label: string;
  summary: string;
  needs_attention: boolean;
  lines: Line[];
  photos: Photo[];
};
type Problem = Stamp & { kind: "script" | "request"; screen: string; message: string; status_code: number | null };
type Activity = {
  people: { id: number; name: string; email: string }[];
  events: TeamEvent[];
  problems: Problem[];
  has_more: boolean;
};

const PAGE = 60;
const PROBLEMS_SHOWN = 5;

/** Fetches its picture (with the owner's sign-in) only once it scrolls into view. */
function Thumb({ photo, onOpen }: { photo: Photo; onOpen: (url: string) => void }) {
  const box = useRef<HTMLButtonElement>(null);
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    const node = box.current;
    if (!node) return;
    let cancel = false;
    let url: string | null = null;
    const watcher = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      watcher.disconnect();
      api
        .get(photo.path, { responseType: "blob" })
        .then((response) => {
          if (cancel) return;
          url = URL.createObjectURL(response.data);
          setSrc(url);
        })
        .catch(() => undefined);
    });
    watcher.observe(node);
    return () => {
      cancel = true;
      watcher.disconnect();
      if (url) URL.revokeObjectURL(url);
    };
  }, [photo.path]);

  return (
    <button
      ref={box}
      type="button"
      className="flex flex-col items-center gap-1 text-[11px] text-zinc-400"
      aria-label={`Open ${photo.label} photo`}
      disabled={!src}
      onClick={() => src && onOpen(src)}
    >
      {src ? <img src={src} alt="" className="h-14 w-14 rounded-xl object-cover" /> : <span className="block h-14 w-14 rounded-xl bg-white/10" />}
      {photo.label}
    </button>
  );
}

export default function TeamActivityPage() {
  const [data, setData] = useState<Activity | null>(null);
  const [events, setEvents] = useState<TeamEvent[]>([]);
  const [person, setPerson] = useState("all");
  const [error, setError] = useState("");
  const [loadingMore, setLoadingMore] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [allProblems, setAllProblems] = useState(false);

  const load = useCallback(async (who: string) => {
    setError("");
    try {
      const params = who === "all" ? { limit: PAGE } : { limit: PAGE, person: who };
      const response = await api.get<Activity>("/api/v1/eleven/team-activity", { params });
      setData(response.data);
      setEvents(response.data.events);
    } catch (err) {
      setError(getErrorMessage(err, "Team activity could not be loaded."));
    }
  }, []);

  useEffect(() => {
    void load(person);
  }, [load, person]);

  async function more() {
    if (!events.length) return;
    setLoadingMore(true);
    try {
      const params = {
        limit: PAGE,
        before: events[events.length - 1].id,
        ...(person === "all" ? {} : { person }),
      };
      const response = await api.get<Activity>("/api/v1/eleven/team-activity", { params });
      setEvents((current) => [...current, ...response.data.events]);
      setData((current) => (current ? { ...current, has_more: response.data.has_more } : current));
    } catch (err) {
      setError(getErrorMessage(err, "More activity could not be loaded."));
    } finally {
      setLoadingMore(false);
    }
  }

  const days: { day: string; items: TeamEvent[] }[] = [];
  for (const event of events) {
    const last = days[days.length - 1];
    if (last && last.day === event.day) last.items.push(event);
    else days.push({ day: event.day, items: [event] });
  }

  return (
    <OwnerShell title="Team activity">
      <div className="owner-premium-stack">
        <p className="text-sm text-zinc-400">
          What your team did and what went wrong on their screens. Times are East Africa Time. Read only: nobody&apos;s account is opened.
        </p>
        {data && (
          <label className="block text-sm text-zinc-400">
            Person
            <select
              className="owner-glass-inner mt-1 block w-full rounded-xl bg-transparent px-3 py-2 text-[var(--text)]"
              value={person}
              onChange={(event) => setPerson(event.target.value)}
            >
              <option value="all">Everyone</option>
              {data.people.map((entry) => (
                <option key={entry.id} value={String(entry.id)}>
                  {data.people.filter((other) => other.name === entry.name).length > 1 ? `${entry.name} (${entry.email})` : entry.name}
                </option>
              ))}
            </select>
          </label>
        )}
        {error && <p className="text-sm text-red-300">{error}</p>}
        {!data && !error && <p className="text-sm text-zinc-400">Loading…</p>}
        {data && (
          <>
            <section className="owner-glass-panel p-5" aria-label="Problems">
              <h2 className="text-lg font-light text-[var(--text)]">Problems</h2>
              {data.problems.length === 0 ? (
                <p className="mt-2 text-sm text-zinc-400">No screen problems reported.</p>
              ) : (
                <ul className="mt-3 space-y-2 text-sm">
                  {(allProblems ? data.problems : data.problems.slice(0, PROBLEMS_SHOWN)).map((problem) => (
                    <li key={problem.id} className="owner-glass-inner">
                      <div className="flex justify-between gap-2">
                        <strong className="font-medium text-[var(--text)]">{problem.person_name}</strong>
                        <span className="text-zinc-400">
                          {problem.day}, {problem.time}
                        </span>
                      </div>
                      <p className="mt-1 text-zinc-300">{problem.message}</p>
                      <p className="mt-1 text-xs text-zinc-500">
                        {problem.screen} · {problem.kind === "request" ? `request failed${problem.status_code ? ` (${problem.status_code})` : ""}` : "screen error"}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
              {data.problems.length > PROBLEMS_SHOWN && (
                <button type="button" className="leviii-btn-ghost mt-3 px-4 py-2 text-sm" onClick={() => setAllProblems(!allProblems)}>
                  {allProblems ? "Show fewer" : `Show all ${data.problems.length}`}
                </button>
              )}
            </section>
            {events.length === 0 && <p className="text-sm text-zinc-400">Nothing yet. Entries appear as your team signs in and works.</p>}
            {days.map((group) => (
              <section key={group.day} className="owner-glass-panel p-5">
                <h2 className="text-base font-light text-[var(--text)]">{group.day}</h2>
                <ul className="mt-3 space-y-3">
                  {group.items.map((event) => (
                    <li key={event.id} className="owner-glass-inner">
                      <div className="flex justify-between gap-2 text-sm">
                        <strong className="font-medium text-[var(--text)]">{event.person_name}</strong>
                        <span className="shrink-0 text-zinc-400">{event.time} EAT</span>
                      </div>
                      <p className={`mt-1 text-sm ${event.needs_attention ? "text-[var(--warning)]" : "text-zinc-200"}`}>{event.label}</p>
                      {event.summary && <p className="mt-1 text-xs text-zinc-400">{event.summary}</p>}
                      {event.lines.length > 0 && (
                        <ul className="mt-2 space-y-0.5 text-xs text-zinc-300">
                          {event.lines.map((line, index) => (
                            <li key={`${line.item}-${index}`}>
                              {line.quantity} {line.unit} {line.item}
                            </li>
                          ))}
                        </ul>
                      )}
                      {event.photos.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-2">
                          {event.photos.map((photo) => (
                            <Thumb key={photo.path} photo={photo} onOpen={setOpen} />
                          ))}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            ))}
            {data.has_more && (
              <button type="button" className="leviii-btn-ghost px-4 py-2 text-sm" disabled={loadingMore} onClick={more}>
                {loadingMore ? "Loading…" : "Show older"}
              </button>
            )}
          </>
        )}
      </div>
      {open && (
        <button type="button" className="fixed inset-0 z-[80] flex items-center justify-center bg-black/90 p-4" onClick={() => setOpen(null)}>
          <img src={open} alt="Full size" className="max-h-full max-w-full" />
        </button>
      )}
    </OwnerShell>
  );
}
