"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import OwnerShell from "@/components/eleven/OwnerShell";
import api from "@/lib/api";

type Overview = {
  on_shift_today: { name: string; role_title: string }[];
  week_schedule: { name: string; role_title: string; weekly_hours: number; slots: { day_name: string; start_time: string; end_time: string }[] }[];
  overwork_warnings: string[];
  labour_cost_today_cents: number | null;
  shift_sales_status: string;
};

export default function ElevenTeamPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/api/v1/team/overview").then((r) => setData(r.data)).catch(() => setError("Team overview could not be loaded."));
  }, []);

  return (
    <OwnerShell title="Team">
      <div className="owner-premium-stack">
        <p className="text-sm text-zinc-400">
          Who is on today, the week&apos;s hours, and labour guardrails. Sales per shift:{" "}
          <span className="text-[var(--text)]">{data?.shift_sales_status === "coming" ? "Coming" : "Live"}</span> until POS receipts land.
        </p>
        {error && <p className="text-sm text-red-300">{error}</p>}
        {!data && !error && <p className="text-sm text-zinc-400">Loading…</p>}
        {data && (
          <>
            <section className="owner-glass-panel p-5">
              <h2 className="text-lg font-light text-[var(--text)]">On shift today</h2>
              {data.on_shift_today.length === 0 ? (
                <p className="mt-2 text-sm text-zinc-400">Nobody is scheduled on the floor right now.</p>
              ) : (
                <ul className="mt-3 space-y-2 text-sm">
                  {data.on_shift_today.map((row) => (
                    <li key={row.name} className="owner-glass-inner flex justify-between gap-2">
                      <span className="text-[var(--text)]">{row.name}</span>
                      <span className="text-zinc-400">{row.role_title}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            {data.overwork_warnings.length > 0 && (
              <section className="owner-oat-highlight">
                <h2 className="text-base font-light text-[var(--warning)]">Overwork warnings</h2>
                <ul className="mt-2 space-y-1 text-sm text-zinc-300">
                  {data.overwork_warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              </section>
            )}
            {data.labour_cost_today_cents != null && (
              <p className="text-sm text-zinc-400">
                Labour cost today: {(data.labour_cost_today_cents / 100).toLocaleString("en-KE")} KES
              </p>
            )}
            <section className="owner-glass-panel p-5">
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-lg font-light text-[var(--text)]">This week</h2>
                <Link href="/eleven/schedule" className="leviii-btn-ghost px-4 py-2 text-sm">
                  Edit schedule
                </Link>
              </div>
              <ul className="mt-3 space-y-3">
                {data.week_schedule.map((person) => (
                  <li key={person.name} className="owner-glass-inner text-sm">
                    <p className="font-medium text-[var(--text)]">
                      {person.name} · {person.role_title}
                    </p>
                    <p className="text-xs text-zinc-400">{person.weekly_hours}h scheduled</p>
                    {person.slots.length > 0 ? (
                      <ul className="mt-2 space-y-1 text-zinc-300">
                        {person.slots.map((s) => (
                          <li key={`${person.name}-${s.day_name}`}>
                            {s.day_name} {s.start_time}–{s.end_time}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-2 text-zinc-500">No weekly pattern yet.</p>
                    )}
                  </li>
                ))}
              </ul>
            </section>
            <Link href="/eleven/settings/team-rules" className="text-sm text-[var(--accent)] underline">
              Team rules
            </Link>
          </>
        )}
      </div>
    </OwnerShell>
  );
}