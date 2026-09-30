"use client";
// One page shape for every part of the Demo Restaurant. Each page explains itself in plain
// words first (what this means, what needs attention, what we suggest and why), and keeps
// the evidence table for last. Everything shown here is calculated by the demo API.
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ChevronRight, Info, Lightbulb } from "lucide-react";
import api from "@/lib/api";
import { getWithFallback } from "@/lib/retry";
import { fmtKes } from "@/lib/format";
import DemoSimulation from "./DemoSimulation";
import { RenderChart, type DemoChart } from "./DemoCharts";

type Attention = { id: string; title: string; why: string; what_to_do: string; level: "urgent" | "watch" | "info"; impact: string | null };
type Decision = { idea: string; why: string; next_step: string; expected: string | null };
type ForecastDay = { date: string; day: string; revenue: number; low: number; high: number; why: string };
type Area = {
  title: string;
  subtitle: string;
  headline: string;
  how_to_read: string;
  metrics: { label: string; value: string | number }[];
  columns: string[];
  rows: (string | number)[][];
  table_title: string;
  table_note: string;
  action: string;
  attention: Attention[];
  decisions: Decision[];
  charts: DemoChart[];
  extra_tables?: { title: string; note: string; columns: string[]; rows: (string | number)[][] }[];
  forecast: ForecastDay[];
  forecast_method: string;
};

const LEVEL = {
  urgent: { label: "Urgent", tone: "hsl(0 60% 48%)" },
  watch: { label: "Keep an eye on", tone: "hsl(35 80% 42%)" },
  info: { label: "For your information", tone: "hsl(201 47% 29%)" },
} as const;

export default function DemoAreaClient({
  areaKey,
  view,
}: {
  areaKey: string;
  view: { title: string; description: string };
}) {
  const [loaded, setLoaded] = useState<{ key: string; data?: Area; error?: boolean; stale?: boolean } | null>(null);
  const [retry, setRetry] = useState(0);
  const [picked, setPicked] = useState<string | null>(null);
  const [done, setDone] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    let active = true;
    getWithFallback(`area:${areaKey}`, () => api.get<Area>(`/api/v1/demo/areas/${areaKey}`))
      .then((r) => {
        if (active) setLoaded({ key: areaKey, data: r.data, stale: r.stale });
      })
      .catch(() => {
        if (active) setLoaded({ key: areaKey, error: true });
      });
    return () => {
      active = false;
    };
  }, [areaKey, retry]);

  const data = loaded?.key === areaKey ? loaded.data : undefined;
  // Start on the quietest coming day: that is the one an owner most wants explained.
  const quietest = useMemo(
    () => (data?.forecast.length ? data.forecast.reduce((lo, d) => (d.revenue < lo.revenue ? d : lo)).date : null),
    [data],
  );
  const selectedDate = picked ?? quietest;
  const selected = data?.forecast.find((d) => d.date === selectedDate) ?? null;
  const open = data?.attention.filter((a) => !done.has(a.id)) ?? [];
  const oneWord = (data?.title ?? view.title).toLowerCase();

  return (
    <div className="space-y-7 animate-rise-in">
      <Link href="/demo" className="text-sm text-[var(--v-primary)]">
        ← Back to Home
      </Link>
      <div>
        <p className="text-xs uppercase tracking-widest text-[var(--v-muted-foreground)]">Demo Restaurant</p>
        <h1 className="font-display mt-2 text-4xl">{(data?.title ?? view.title)}.</h1>
        <p className="mt-3 text-sm">{data?.subtitle ?? view.description}</p>
      </div>
      {loaded?.error ? (
        <div role="alert">
          This page could not load.{" "}
          <button
            className="underline"
            onClick={() => {
              setLoaded(null);
              setRetry((v) => v + 1);
            }}
          >
            Try again
          </button>
        </div>
      ) : !data ? (
        <p role="status">Loading the sample analysis…</p>
      ) : (
        <>
          {loaded?.stale && <p role="status" className="flex flex-wrap items-center gap-2 rounded-lg border border-[hsl(43_76%_57%_/_0.6)] bg-[hsl(42_71%_75%_/_0.18)] px-3 py-2 text-xs">We could not reach the service just now, so you are seeing the last view that loaded. <button type="button" onClick={() => { setLoaded(null); setRetry((v) => v + 1); }} className="font-semibold text-[var(--v-primary)] underline">Try again</button></p>}
          <section className="rounded-xl border border-[hsl(201_47%_29%_/_0.25)] bg-[hsl(201_47%_29%_/_0.05)] p-5">
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--v-muted-foreground)]">In plain words</p>
            <p className="font-display mt-2 text-xl leading-snug">{data.headline}</p>
            <p className="mt-3 flex items-start gap-2 text-xs leading-relaxed text-[var(--v-muted-foreground)]">
              <Info size={14} className="mt-0.5 shrink-0 text-[var(--v-primary)]" />
              <span>{data.how_to_read}</span>
            </p>
          </section>

          <div className="grid gap-3 sm:grid-cols-3">
            {data.metrics.map((m) => (
              <article key={m.label} className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5">
                <p className="text-xs text-[var(--v-muted-foreground)]">{m.label}</p>
                <p className="font-display mt-3 text-2xl">{m.value}</p>
              </article>
            ))}
          </div>

          {data.charts.map((chart) => (
            <RenderChart key={chart.title} chart={chart} selectedDate={selectedDate} onSelectDate={setPicked} />
          ))}

          {data.forecast.length > 0 && (
            <section aria-labelledby="ahead-heading">
              <h2 id="ahead-heading" className="font-display text-2xl">
                What we expect over the next 7 days
              </h2>
              <p className="my-3 text-xs text-[var(--v-muted-foreground)]">{data.forecast_method}</p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
                {data.forecast.map((r) => {
                  const on = r.date === selectedDate;
                  return (
                    <button
                      key={r.date}
                      type="button"
                      aria-pressed={on}
                      onClick={() => setPicked(r.date)}
                      className={`rounded-xl border p-3 text-left transition ${on ? "border-[var(--v-primary)] bg-[hsl(201_47%_29%_/_0.07)]" : "border-[var(--v-border)] bg-[var(--v-card)] hover:border-[var(--v-primary)]/50"}`}
                    >
                      <p className="text-xs font-semibold">{r.day}</p>
                      <p className="text-[10px] text-[var(--v-muted-foreground)]">{r.date.slice(5)}</p>
                      <p className="font-display my-1.5 text-lg">{fmtKes(r.revenue)}</p>
                      <p className="text-[10px] text-[var(--v-muted-foreground)]">
                        {fmtKes(r.low)}–{fmtKes(r.high)}
                      </p>
                    </button>
                  );
                })}
              </div>
              {selected && (
                <div aria-live="polite" className="mt-3 rounded-xl border border-[hsl(43_76%_57%_/_0.6)] bg-[hsl(42_71%_75%_/_0.18)] p-4">
                  <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">
                    Why {selected.day} looks like this
                  </p>
                  <p className="mt-2 text-sm leading-relaxed">{selected.why}</p>
                </div>
              )}
            </section>
          )}

          <section aria-labelledby="attention-heading">
            <h2 id="attention-heading" className="font-display mb-3 text-2xl">
              What needs your attention here
            </h2>
            {open.length === 0 ? (
              <p className="rounded-xl border border-[hsl(150_28%_41%_/_0.24)] bg-[hsl(150_28%_41%_/_0.06)] p-4 text-sm">
                {data.attention.length === 0 ? "Nothing urgent here right now." : "You have looked at everything on this page."}
              </p>
            ) : (
              <div className="space-y-3">
                {open.map((a) => (
                  <article key={a.id} className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <AlertTriangle size={15} style={{ color: LEVEL[a.level].tone }} />
                      <span className="text-[10px] font-bold uppercase tracking-[0.14em]" style={{ color: LEVEL[a.level].tone }}>
                        {LEVEL[a.level].label}
                      </span>
                      {a.impact && <span className="text-[10px] font-semibold text-[var(--v-primary)]">· {a.impact}</span>}
                    </div>
                    <h3 className="mt-2 text-sm font-bold">{a.title}</h3>
                    <div className="mt-3 grid gap-3 border-t border-[var(--v-border)] pt-3 sm:grid-cols-2">
                      <div>
                        <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">Why</p>
                        <p className="mt-1 text-xs leading-relaxed">{a.why}</p>
                      </div>
                      <div>
                        <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">What to do</p>
                        <p className="mt-1 text-xs leading-relaxed">{a.what_to_do}</p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => setDone((s) => new Set(s).add(a.id))}
                      className="mt-3 min-h-9 rounded-lg border border-[var(--v-border)] px-3 py-2 text-[11px] font-bold hover:bg-[var(--v-muted)]"
                    >
                      Got it
                    </button>
                  </article>
                ))}
              </div>
            )}
            <p className="mt-2 text-[11px] text-[var(--v-muted-foreground)]">Demo only: this hides the card on this page. No business records change.</p>
          </section>

          {data.decisions.length > 0 && (
            <section aria-labelledby="ideas-heading">
              <h2 id="ideas-heading" className="font-display mb-1 text-2xl">
                What we suggest, and why
              </h2>
              <p className="mb-3 text-xs text-[var(--v-muted-foreground)]">Ideas worked out from your numbers. They are chances to try, not results.</p>
              <div className="grid gap-3 sm:grid-cols-2">
                {data.decisions.map((d) => (
                  <article key={d.idea} className="flex flex-col rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-4">
                    <div className="flex items-start gap-2">
                      <Lightbulb size={16} className="mt-0.5 shrink-0 text-[hsl(35_80%_42%)]" />
                      <h3 className="text-sm font-bold leading-snug">{d.idea}</h3>
                    </div>
                    <p className="mt-3 text-xs leading-relaxed">
                      <b>Why: </b>
                      {d.why}
                    </p>
                    <p className="mt-2 text-xs leading-relaxed">
                      <b>Next step: </b>
                      {d.next_step}
                    </p>
                    {d.expected && <p className="mt-3 text-[11px] font-semibold text-[var(--v-primary)]">{d.expected}</p>}
                  </article>
                ))}
              </div>
            </section>
          )}

          {["menu", "intelligence", "finance"].includes(areaKey) && <DemoSimulation />}

          {(data.extra_tables ?? []).map((t) => (
            <section key={t.title} className="overflow-x-auto rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5">
              <h2 className="font-display text-xl">{t.title}</h2>
              <p className="mb-4 mt-1 text-xs text-[var(--v-muted-foreground)]">{t.note}</p>
              <table className="w-full text-left text-sm">
                <thead>
                  <tr>
                    {t.columns.map((c) => (
                      <th scope="col" className="border-b border-[var(--v-border)] p-3 text-xs font-semibold text-[var(--v-muted-foreground)]" key={c}>
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {t.rows.map((row, i) => (
                    <tr key={i}>
                      {row.map((v, j) => (
                        <td className="border-b border-[var(--v-border)] p-3 align-top" key={j}>
                          {v}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          ))}

          <section className="overflow-x-auto rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5">
            <h2 className="font-display text-xl">{data.table_title}</h2>
            <p className="mb-4 mt-1 text-xs text-[var(--v-muted-foreground)]">{data.table_note}</p>
            <table className="w-full text-left text-sm">
              <thead>
                <tr>
                  {data.columns.map((c) => (
                    <th scope="col" className="border-b border-[var(--v-border)] p-3 text-xs font-semibold text-[var(--v-muted-foreground)]" key={c}>
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row, i) => (
                  <tr key={i}>
                    {row.map((v, j) => (
                      <td className="border-b border-[var(--v-border)] p-3 align-top" key={j}>
                        {v}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <Link
            className="inline-flex items-center gap-1 text-sm font-semibold text-[var(--v-primary)]"
            href={`/demo/os?topic=${areaKey}&q=${encodeURIComponent(`What should I do about ${oneWord}?`)}`}
          >
            Want to talk this through? Ask OS <ChevronRight size={14} />
          </Link>
        </>
      )}
    </div>
  );
}
