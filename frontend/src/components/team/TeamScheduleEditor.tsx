"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

type BoardMember = {
  staff_member_id: number;
  name: string;
  role_title: string;
  compact_lines: string[];
  weekly_hours: number;
  weekdays: number[];
};

type Slot = { staff_member_id: number; weekday: number; start_time: string; end_time: string };

type Board = {
  slots: Slot[];
  members: BoardMember[];
  roster: { id: number; name: string; role_title: string }[];
  today_weekday: number;
  scheduled_today_ids: number[];
  today: string;
};

function slotsForMember(slots: Slot[], memberId: number): Slot[] {
  return slots.filter((s) => s.staff_member_id === memberId);
}

export default function TeamScheduleEditor() {
  const [board, setBoard] = useState<Board | null>(null);
  const [slots, setSlots] = useState<Slot[]>([]);
  const [memberId, setMemberId] = useState<number | "">("");
  const [selectedDays, setSelectedDays] = useState<Set<number>>(new Set());
  const [start, setStart] = useState("09:00");
  const [end, setEnd] = useState("17:00");
  const [perDay, setPerDay] = useState<Record<number, { start: string; end: string }>>({});
  const [usePerDay, setUsePerDay] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const { data } = await api.get<Board>("/api/v1/team/weekly-slots");
    setBoard(data);
    setSlots(data.slots);
    if (data.roster[0] && memberId === "") setMemberId(data.roster[0].id);
  }, [memberId]);

  useEffect(() => {
    load().catch(() => setError("Schedule could not be loaded."));
  }, [load]);

  const summary = useMemo(() => {
    if (!board || memberId === "") return null;
    return board.members.find((m) => m.staff_member_id === memberId) ?? null;
  }, [board, memberId]);

  useEffect(() => {
    if (memberId === "" || !board) return;
    const memberSlots = slotsForMember(slots, Number(memberId));
    setSelectedDays(new Set(memberSlots.map((s) => s.weekday)));
    if (memberSlots[0]) {
      setStart(memberSlots[0].start_time);
      setEnd(memberSlots[0].end_time);
    }
    const overrides: Record<number, { start: string; end: string }> = {};
    memberSlots.forEach((s) => {
      overrides[s.weekday] = { start: s.start_time, end: s.end_time };
    });
    setPerDay(overrides);
    const times = new Set(memberSlots.map((s) => `${s.start_time}|${s.end_time}`));
    setUsePerDay(times.size > 1);
  }, [memberId, board, slots]);

  function toggleDay(day: number) {
    setSelectedDays((prev) => {
      const next = new Set(prev);
      if (next.has(day)) next.delete(day);
      else next.add(day);
      return next;
    });
  }

  function applyPattern() {
    if (memberId === "") return;
    const id = Number(memberId);
    const others = slots.filter((s) => s.staff_member_id !== id);
    const next: Slot[] = [...others];
    selectedDays.forEach((weekday) => {
      const span = usePerDay && perDay[weekday] ? perDay[weekday] : { start, end };
      next.push({
        staff_member_id: id,
        weekday,
        start_time: span.start,
        end_time: span.end,
      });
    });
    setSlots(next);
    setMessage("Pattern updated — tap Save to keep it.");
  }

  function buildPayload(): Slot[] {
    if (memberId === "") return slots;
    const mid = Number(memberId);
    const others = slots.filter((s) => s.staff_member_id !== mid);
    const next: Slot[] = [...others];
    selectedDays.forEach((weekday) => {
      const span = usePerDay && perDay[weekday] ? perDay[weekday] : { start, end };
      next.push({ staff_member_id: mid, weekday, start_time: span.start, end_time: span.end });
    });
    return next;
  }

  async function save() {
    setError("");
    setMessage("");
    const payload = buildPayload();
    setSlots(payload);
    try {
      const response = await api.put("/api/v1/team/weekly-slots", { slots: payload });
      setMessage(
        response.data.status === "needs_owner_approval"
          ? "Sent to the owner — schedule breaks a team rule."
          : "Schedule saved.",
      );
      await load();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Schedule was not saved.");
    }
  }

  async function markMissed(kind: "missed" | "swap", swapTo?: number) {
    if (memberId === "" || !board) return;
    setError("");
    try {
      await api.post("/api/v1/team/day-override", {
        staff_member_id: Number(memberId),
        shift_date: board.today,
        kind,
        swap_staff_member_id: swapTo ?? null,
      });
      setMessage(kind === "missed" ? "Marked missed for today." : "Swap recorded for today.");
      await load();
    } catch {
      setError(kind === "missed" ? "Could not mark missed." : "Could not record the swap.");
    }
  }

  const scheduledToday = board && memberId !== "" && board.scheduled_today_ids.includes(Number(memberId));

  return (
    <div className="owner-premium-stack">
      <p className="text-sm text-zinc-400">Set each person&apos;s usual week once. One save updates everyone.</p>
      {error && <p className="text-sm text-red-300">{error}</p>}
      {message && <p className="text-sm text-[var(--text)]">{message}</p>}
      <section className="owner-glass-panel space-y-4 p-5">
        <label className="block text-sm">
          Team member
          <select
            className="leviii-input mt-1 w-full rounded-2xl px-3 py-2"
            value={memberId}
            onChange={(e) => setMemberId(e.target.value ? Number(e.target.value) : "")}
          >
            {board?.roster.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.role_title})
              </option>
            ))}
          </select>
        </label>
        {summary && (
          <p className="text-xs text-zinc-400">
            {summary.weekly_hours}h scheduled
            {summary.compact_lines.length > 0 ? ` · ${summary.compact_lines.join("; ")}` : " · no pattern yet"}
          </p>
        )}
        <div className="grid grid-cols-7 gap-1">
          {DAY_LABELS.map((label, weekday) => {
            const on = selectedDays.has(weekday);
            return (
              <button
                key={label}
                type="button"
                onClick={() => toggleDay(weekday)}
                className={`rounded-xl py-2 text-xs font-medium ${on ? "bg-[var(--accent)] text-[var(--on-accent)]" : "bg-[var(--surface)] text-zinc-400"}`}
              >
                {label}
              </button>
            );
          })}
        </div>
        <label className="flex items-center gap-2 text-sm text-zinc-300">
          <input type="checkbox" checked={usePerDay} onChange={(e) => setUsePerDay(e.target.checked)} />
          Different times per day
        </label>
        {usePerDay ? (
          <ul className="space-y-2 text-sm">
            {DAY_LABELS.map((label, weekday) =>
              selectedDays.has(weekday) ? (
                <li key={label} className="flex flex-wrap items-center gap-2">
                  <span className="w-10 text-zinc-400">{label}</span>
                  <input
                    className="leviii-input w-24 rounded-xl px-2 py-1"
                    value={perDay[weekday]?.start ?? start}
                    onChange={(e) =>
                      setPerDay((p) => ({ ...p, [weekday]: { start: e.target.value, end: p[weekday]?.end ?? end } }))
                    }
                  />
                  <span className="text-zinc-500">–</span>
                  <input
                    className="leviii-input w-24 rounded-xl px-2 py-1"
                    value={perDay[weekday]?.end ?? end}
                    onChange={(e) =>
                      setPerDay((p) => ({ ...p, [weekday]: { start: p[weekday]?.start ?? start, end: e.target.value } }))
                    }
                  />
                </li>
              ) : null,
            )}
          </ul>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            <label className="block text-sm">
              Start
              <input className="leviii-input mt-1 w-full rounded-2xl px-3 py-2" value={start} onChange={(e) => setStart(e.target.value)} />
            </label>
            <label className="block text-sm">
              End
              <input className="leviii-input mt-1 w-full rounded-2xl px-3 py-2" value={end} onChange={(e) => setEnd(e.target.value)} />
            </label>
          </div>
        )}
        <button type="button" onClick={applyPattern} className="leviii-btn-ghost w-full py-2 text-sm">
          Apply to selected days
        </button>
        <button type="button" onClick={save} className="leviii-btn-primary w-full py-2 text-sm">
          Save schedule
        </button>
        {scheduledToday && (
          <div className="space-y-2 border-t border-white/5 pt-3">
            <p className="text-xs text-zinc-400">Scheduled today</p>
            <button type="button" onClick={() => markMissed("missed")} className="leviii-btn-ghost w-full py-2 text-sm">
              Mark missed today
            </button>
            <label className="block text-sm">
              Same-day cover
              <select
                className="leviii-input mt-1 w-full rounded-2xl px-3 py-2"
                defaultValue=""
                onChange={(e) => {
                  const v = Number(e.target.value);
                  if (v) markMissed("swap", v);
                }}
              >
                <option value="">Who covered?</option>
                {board?.roster
                  .filter((p) => p.id !== memberId)
                  .map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
              </select>
            </label>
          </div>
        )}
      </section>
    </div>
  );
}