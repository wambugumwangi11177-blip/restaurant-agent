"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import api from "@/lib/api";

type Overview = {
  on_shift_now: { name: string; role_title: string; window?: string }[];
  week_schedule: {
    name: string;
    role_title: string;
    weekly_hours: number;
    compact_lines: string[];
  }[];
  overwork_warnings: string[];
  labour_cost_today_cents: number | null;
  shift_sales_status: string;
};

export default function StoreTeamPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/api/v1/team/overview").then((r) => setData(r.data)).catch(() => setError("Team overview could not be loaded."));
  }, []);

  return (
    <div className="owner-premium-stack">
      <p className="text-sm text-zinc-400">
        Who is on the floor right now and this week&apos;s hours. Sales per shift:{" "}
        <span className="text-[var(--text)]">
          {data?.shift_sales_status === "coming" ? "coming once your till is connected." : "shown from receipts."}
        </span>
      </p>
      {error && <p className="text-sm text-red-300">{error}</p>}
      {!data && !error && <p className="text-sm text-zinc-400">Loading…</p>}
      {data && (
        <>
          <section className="owner-glass-panel p-5">
            <h2 className="text-lg font-light text-[var(--text)]">On shift now</h2>
            {data.on_shift_now.length === 0 ? (
              <p className="mt-2 text-sm text-zinc-400">Nobody is in their scheduled window right now.</p>
            ) : (
              <ul className="mt-3 space-y-2 text-sm">
                {data.on_shift_now.map((row) => (
                  <li key={row.name} className="owner-glass-inner flex justify-between gap-2">
                    <span className="text-[var(--text)]">{row.name}</span>
                    <span className="text-zinc-400">
                      {row.role_title}
                      {row.window ? ` · ${row.window}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
          {data.overwork_warnings.length > 0 && (
            <section className="owner-oat-highlight">
              <h2 className="text-base font-light text-[var(--warning)]">Hours warnings</h2>
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
              <Link href="/store/schedule" className="leviii-btn-ghost px-4 py-2 text-sm">
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
                  {person.compact_lines?.length ? (
                    <ul className="mt-2 space-y-1 text-zinc-300">
                      {person.compact_lines.map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-2 text-zinc-500">No weekly pattern yet.</p>
                  )}
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}