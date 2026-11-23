"use client";

import { useEffect, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import api from "@/lib/api";

type RosterRow = { id: number; name: string; role_title: string; has_login: boolean };
type Slot = { staff_member_id: number; weekday: number; start_time: string; end_time: string };

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function ElevenSchedulePage() {
  const [roster, setRoster] = useState<RosterRow[]>([]);
  const [slots, setSlots] = useState<Slot[]>([]);
  const [memberId, setMemberId] = useState<number | "">("");
  const [weekday, setWeekday] = useState(0);
  const [start, setStart] = useState("09:00");
  const [end, setEnd] = useState("17:00");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    const [r, s] = await Promise.all([
      api.get("/api/v1/team/roster"),
      api.get("/api/v1/team/weekly-slots"),
    ]);
    setRoster(r.data);
    setSlots(s.data);
    if (r.data[0] && memberId === "") setMemberId(r.data[0].id);
  }

  useEffect(() => {
    refresh().catch(() => setError("Schedule could not be loaded."));
  }, []);

  function addSlot() {
    if (memberId === "") return;
    setSlots((prev) => [
      ...prev.filter((x) => !(x.staff_member_id === memberId && x.weekday === weekday)),
      { staff_member_id: Number(memberId), weekday, start_time: start, end_time: end },
    ]);
  }

  async function save() {
    setError("");
    setMessage("");
    try {
      const response = await api.put("/api/v1/team/weekly-slots", { slots });
      setMessage(
        response.data.status === "needs_owner_approval"
          ? "Sent to the owner — schedule breaks a team rule."
          : "Schedule saved.",
      );
      await refresh();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Schedule was not saved.");
    }
  }

  async function markMissed() {
    if (memberId === "") return;
    setError("");
    try {
      await api.post("/api/v1/team/day-override", {
        staff_member_id: Number(memberId),
        shift_date: new Date().toISOString().slice(0, 10),
        kind: "missed",
      });
      setMessage("Marked missed for today.");
    } catch {
      setError("Could not mark missed.");
    }
  }

  return (
    <OwnerShell title="Schedule">
      <div className="owner-premium-stack">
        <p className="text-sm text-zinc-400">Set each person&apos;s usual week once; tap missed when they did not come in today.</p>
        {error && <p className="text-sm text-red-300">{error}</p>}
        {message && <p className="text-sm text-[var(--text)]">{message}</p>}
        <section className="owner-glass-panel space-y-3 p-5">
          <label className="block text-sm">
            Team member
            <select
              className="leviii-input mt-1 w-full rounded-2xl px-3 py-2"
              value={memberId}
              onChange={(e) => setMemberId(e.target.value ? Number(e.target.value) : "")}
            >
              {roster.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.role_title})
                </option>
              ))}
            </select>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block text-sm">
              Day
              <select className="leviii-input mt-1 w-full rounded-2xl px-3 py-2" value={weekday} onChange={(e) => setWeekday(Number(e.target.value))}>
                {DAYS.map((d, i) => (
                  <option key={d} value={i}>
                    {d}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              Start
              <input className="leviii-input mt-1 w-full rounded-2xl px-3 py-2" value={start} onChange={(e) => setStart(e.target.value)} />
            </label>
            <label className="block text-sm">
              End
              <input className="leviii-input mt-1 w-full rounded-2xl px-3 py-2" value={end} onChange={(e) => setEnd(e.target.value)} />
            </label>
          </div>
          <button type="button" onClick={addSlot} className="leviii-btn-ghost w-full py-2 text-sm">
            Add to weekly pattern
          </button>
          <button type="button" onClick={save} className="leviii-btn-primary w-full py-2 text-sm">
            Save schedule
          </button>
          <button type="button" onClick={markMissed} className="leviii-btn-ghost w-full py-2 text-sm">
            Mark missed today
          </button>
        </section>
        <section className="owner-glass-panel p-5 text-sm text-zinc-300">
          <h2 className="mb-2 text-base font-light text-[var(--text)]">Current pattern</h2>
          {slots.length === 0 ? (
            <p className="text-zinc-400">No slots yet.</p>
          ) : (
            <ul className="space-y-1">
              {slots.map((s) => {
                const person = roster.find((p) => p.id === s.staff_member_id);
                return (
                  <li key={`${s.staff_member_id}-${s.weekday}`}>
                    {person?.name ?? s.staff_member_id} · {DAYS[s.weekday]} {s.start_time}–{s.end_time}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>
    </OwnerShell>
  );
}