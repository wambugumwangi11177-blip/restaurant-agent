"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import api from "@/lib/api";
import { fmtKes } from "@/lib/format";
import DemoSimulation from "./DemoSimulation";
type Area = {
  metrics: { label: string; value: string | number }[];
  columns: string[];
  rows: (string | number)[][];
  action: string;
  forecast: { date: string; revenue: number; low: number; high: number }[];
  forecast_method: string;
  trend: { date: string; revenue: number }[];
};
export default function DemoAreaClient({
  areaKey,
  view,
}: {
  areaKey: string;
  view: { title: string; description: string };
}) {
  const [loaded, setLoaded] = useState<{
    key: string;
    data?: Area;
    error?: boolean;
  } | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    api
      .get<Area>(`/api/v1/demo/areas/${areaKey}`)
      .then((r) => {
        if (active) setLoaded({ key: areaKey, data: r.data });
      })
      .catch(() => {
        if (active) setLoaded({ key: areaKey, error: true });
      });
    return () => {
      active = false;
    };
  }, [areaKey, retry]);
  const data = loaded?.key === areaKey ? loaded.data : undefined;
  return (
    <div className="space-y-7 animate-rise-in">
      <Link href="/demo" className="text-sm text-[var(--v-primary)]">
        ← Back to Home
      </Link>
      <div>
        <p className="text-xs uppercase tracking-widest text-[var(--v-muted-foreground)]">
          Demo Restaurant
        </p>
        <h1 className="font-display mt-2 text-4xl">{view.title}.</h1>
        <p className="mt-3 text-sm">{view.description}</p>
      </div>
      {loaded?.error ? (
        <div role="alert">
          This area could not load.{" "}
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
          <div className="grid gap-3 sm:grid-cols-3">
            {data.metrics.map((m) => (
              <article
                key={m.label}
                className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5"
              >
                <p className="text-xs text-[var(--v-muted-foreground)]">
                  {m.label}
                </p>
                <p className="font-display mt-3 text-2xl">{m.value}</p>
              </article>
            ))}
          </div>
          {data.trend.length > 0 && (
            <section className="rounded-xl border border-[var(--v-border)] p-5">
              <h2 className="font-display text-xl">
                Sales context · last 7 sample days
              </h2>
              <div
                className="mt-5 flex h-36 items-end gap-3"
                role="img"
                aria-label="Sample daily revenue; exact values below each bar"
              >
                {data.trend.map((r) => (
                  <div
                    key={r.date}
                    className="flex flex-1 flex-col items-center gap-2 text-[10px]"
                  >
                    <div
                      className="w-full rounded-t bg-[var(--v-primary)]"
                      style={{
                        height: Math.max(
                          4,
                          (r.revenue /
                            Math.max(...data.trend.map((x) => x.revenue))) *
                            85,
                        ),
                      }}
                    />
                    <span>{fmtKes(r.revenue)}</span>
                    <span>{r.date.slice(5)}</span>
                  </div>
                ))}
              </div>
            </section>
          )}
          <section className="overflow-x-auto rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5">
            <h2 className="font-display mb-4 text-xl">Supporting evidence</h2>
            <table className="w-full text-left text-sm">
              <thead>
                <tr>
                  {data.columns.map((c) => (
                    <th
                      scope="col"
                      className="border-b border-[var(--v-border)] p-3"
                      key={c}
                    >
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row, i) => (
                  <tr key={i}>
                    {row.map((v, j) => (
                      <td
                        className="border-b border-[var(--v-border)] p-3"
                        key={j}
                      >
                        {v}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          {data.forecast.length > 0 && (
            <section>
              <h2 className="font-display text-2xl">
                Looking ahead · next 7 days
              </h2>
              <p className="my-3 text-xs text-[var(--v-muted-foreground)]">
                {data.forecast_method}
              </p>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {data.forecast.map((r) => (
                  <article
                    className="rounded-xl border border-[var(--v-border)] p-4"
                    key={r.date}
                  >
                    <p className="text-xs">{r.date}</p>
                    <p className="font-display my-2 text-xl">
                      {fmtKes(r.revenue)}
                    </p>
                    <p className="text-xs">
                      Range {fmtKes(r.low)}–{fmtKes(r.high)}
                    </p>
                  </article>
                ))}
              </div>
            </section>
          )}
          <section className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5">
            <h2 className="font-display text-xl">Recommended next step</h2>
            <p className="my-3 text-sm leading-6">{data.action}</p>
            <Link
              className="text-sm font-semibold text-[var(--v-primary)]"
              href={`/demo/os?topic=${areaKey}&q=${encodeURIComponent(`Explain the ${view.title.toLowerCase()} evidence and what I should do next.`)}`}
            >
              Discuss this with OS →
            </Link>
          </section>
          {["menu", "intelligence", "finance"].includes(areaKey) && (
            <DemoSimulation />
          )}
        </>
      )}
    </div>
  );
}
