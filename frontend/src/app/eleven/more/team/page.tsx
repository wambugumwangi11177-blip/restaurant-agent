"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import OwnerShell from "@/components/eleven/OwnerShell";
import api from "@/lib/api";

type Hub = {
  overview: {
    on_shift_now: { name: string; role_title: string; window?: string }[];
    week_schedule: { name: string; role_title: string; weekly_hours: number; compact_lines: string[] }[];
    overwork_warnings: string[];
    labour_cost_today_cents: number | null;
  };
  roster: { id: number; name: string; role_title: string; has_login: boolean; score_note: string }[];
  jack: {
    name: string;
    email: string;
    on_shift: boolean;
    questionnaire: string;
    answers: { prompt: string; label: string }[];
    routing_mode: string;
  } | null;
  pin_handover_history: { at: string | null; action: string; who: string; summary: string }[];
  restock_routing_mode: string;
};

export default function ElevenMoreTeamPage() {
  const [data, setData] = useState<Hub | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<Hub>("/api/v1/eleven/team/hub").then((r) => setData(r.data)).catch(() => setError("Team hub could not be loaded."));
  }, []);

  return (
    <OwnerShell title="Team">
      <div className="owner-premium-stack">
        {error && <p className="text-sm text-red-300">{error}</p>}
        {!data && !error && <p className="text-sm text-zinc-400">Loading…</p>}
        {data && (
          <>
            <section className="owner-glass-panel p-5">
              <h2 className="text-lg font-light text-[var(--text)]">On shift now</h2>
              <ul className="mt-3 space-y-2 text-sm">
                {data.overview.on_shift_now.length === 0 ? (
                  <li className="text-zinc-400">Nobody is in their window right now.</li>
                ) : (
                  data.overview.on_shift_now.map((row) => (
                    <li key={row.name} className="owner-glass-inner flex justify-between gap-2">
                      <span>{row.name}</span>
                      <span className="text-zinc-400">
                        {row.role_title}
                        {row.window ? ` · ${row.window}` : ""}
                      </span>
                    </li>
                  ))
                )}
              </ul>
            </section>

            <section className="owner-glass-panel p-5">
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-lg font-light">Roster</h2>
                <Link href="/eleven/staff" className="leviii-btn-ghost px-3 py-2 text-sm">
                  Add / remove
                </Link>
              </div>
              <ul className="mt-3 space-y-2 text-sm">
                {data.roster.map((m) => (
                  <li key={m.id} className="owner-glass-inner">
                    <p className="text-[var(--text)]">{m.name}</p>
                    <p className="text-xs text-zinc-400">
                      {m.role_title}
                      {m.has_login ? " · has login" : " · no login yet"}
                    </p>
                    <p className="text-xs text-zinc-500">{m.score_note}</p>
                  </li>
                ))}
              </ul>
            </section>

            {data.jack && (
              <section className="owner-glass-panel p-5">
                <h2 className="text-lg font-light">Jack (store)</h2>
                <p className="text-sm text-zinc-400 mt-1">
                  {data.jack.on_shift ? "On shift now" : "Off shift"} · questionnaire: {data.jack.questionnaire}
                </p>
                <p className="text-xs text-zinc-500 mt-2">Restock routing: {data.restock_routing_mode.replace(/_/g, " ")}</p>
                <h3 className="mt-4 text-sm text-zinc-300">Setup answers</h3>
                <ul className="mt-2 space-y-2 text-sm">
                  {data.jack.answers.map((a) => (
                    <li key={a.prompt} className="owner-glass-inner">
                      <p className="text-xs text-zinc-500">{a.prompt}</p>
                      <p>{a.label}</p>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section className="owner-glass-panel p-5">
              <h2 className="text-lg font-light">PIN & handover history</h2>
              <ul className="mt-3 space-y-2 text-sm">
                {data.pin_handover_history.length === 0 ? (
                  <li className="text-zinc-400">No PIN or sign-in resets logged yet.</li>
                ) : (
                  data.pin_handover_history.map((row, i) => (
                    <li key={`${row.at}-${i}`} className="owner-glass-inner">
                      <p className="text-[var(--text)]">{row.action}</p>
                      <p className="text-xs text-zinc-500">
                        {row.who} · {row.at ? new Date(row.at).toLocaleString() : ""}
                      </p>
                      {row.summary && <p className="text-xs text-zinc-400 mt-1">{row.summary}</p>}
                    </li>
                  ))
                )}
              </ul>
              <Link href="/eleven/settings" className="mt-4 inline-block text-sm text-white underline">
                Change your PIN in Settings
              </Link>
            </section>

            <section className="owner-glass-panel p-5">
              <h2 className="text-lg font-light">This week</h2>
              <ul className="mt-3 space-y-3 text-sm">
                {data.overview.week_schedule.map((row) => (
                  <li key={row.name} className="owner-glass-inner">
                    <p className="flex justify-between gap-2">
                      <span>{row.name}</span>
                      <span className="text-zinc-400">{row.weekly_hours}h</span>
                    </p>
                    <p className="text-xs text-zinc-500">{row.compact_lines.join(" · ")}</p>
                  </li>
                ))}
              </ul>
              <Link href="/eleven/schedule" className="leviii-btn-ghost mt-4 inline-flex px-4 py-2 text-sm">
                Edit schedule
              </Link>
            </section>
          </>
        )}
      </div>
    </OwnerShell>
  );
}