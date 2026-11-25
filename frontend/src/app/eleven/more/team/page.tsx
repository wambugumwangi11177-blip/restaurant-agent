"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import OwnerShell from "@/components/eleven/OwnerShell";
import ExplainedCard from "@/components/eleven/charts/ExplainedCard";
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
            <ExplainedCard
              title="On shift now"
              headline={
                data.overview.on_shift_now.length
                  ? `${data.overview.on_shift_now.length} on shift`
                  : "Nobody in their window"
              }
              what="Who is working right now and in which role."
              freshness="Live · from the schedule"
              hasData
              emptyHint="Nobody is in their window right now."
            >
              <ul className="space-y-2 text-sm">
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
            </ExplainedCard>

            <ExplainedCard
              title="Roster"
              headline={`${data.roster.length} people`}
              what="Staff names, roles, and whether they can sign in."
              freshness="As entered · from Settings"
              hasData
              emptyHint="Add staff in Settings."
            >
              <div className="mb-3 flex justify-end">
                <Link href="/eleven/staff" className="leviii-btn-ghost px-3 py-2 text-sm">
                  Add / remove
                </Link>
              </div>
              <ul className="space-y-2 text-sm">
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
            </ExplainedCard>

            {data.jack && (
              <ExplainedCard
                title="Jack (store)"
                headline={data.jack.on_shift ? "Jack is on shift" : "Jack is off shift"}
                sub={`Questionnaire: ${data.jack.questionnaire}`}
                what="Storekeeper setup, routing for restock, and questionnaire answers."
                freshness="As entered · from Jack's setup"
                hasData
                emptyHint="Jack is not configured yet."
              >
                <p className="mb-2 text-xs text-zinc-500">Restock routing: {data.restock_routing_mode.replace(/_/g, " ")}</p>
                <ul className="space-y-2 text-sm">
                  {data.jack.answers.map((a) => (
                    <li key={a.prompt} className="owner-glass-inner">
                      <p className="text-xs text-zinc-500">{a.prompt}</p>
                      <p>{a.label}</p>
                    </li>
                  ))}
                </ul>
              </ExplainedCard>
            )}

            <ExplainedCard
              title="PIN & handover history"
              headline={data.pin_handover_history.length ? `${data.pin_handover_history.length} events` : "No resets yet"}
              what="PIN changes and handover sign-ins, newest first."
              freshness="As entered · from sign-ins"
              hasData
              emptyHint="No PIN or sign-in resets logged yet."
            >
              <ul className="space-y-2 text-sm">
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
            </ExplainedCard>

            <ExplainedCard
              title="This week"
              headline={`${data.overview.week_schedule.length} scheduled`}
              what="Hours and shift lines for each person this week."
              freshness="Live · from the schedule"
              hasData
              emptyHint="Add a schedule to see the week."
            >
              <ul className="space-y-3 text-sm">
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
            </ExplainedCard>
          </>
        )}
      </div>
    </OwnerShell>
  );
}