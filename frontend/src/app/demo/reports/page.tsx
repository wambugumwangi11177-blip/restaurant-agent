"use client";
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { fmtKes } from "@/lib/format";
import DemoCreative from "@/components/demo/DemoCreative";
type Report = {
  period: string;
  range: string;
  revenue: number;
  orders: number;
  report_text: string;
  coverage_days: number;
  top_items: { name: string; qty: number; sales_kes: number }[];
};
export default function DemoReports() {
  const [period, setPeriod] = useState("daily"),
    [loaded, setLoaded] = useState<{
      period: string;
      data?: Report;
      error?: boolean;
    } | null>(null),
    [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    api
      .get<Report>(`/api/v1/demo/reports/${period}`)
      .then((r) => {
        if (active) setLoaded({ period, data: r.data });
      })
      .catch(() => {
        if (active) setLoaded({ period, error: true });
      });
    return () => {
      active = false;
    };
  }, [period, retry]);
  const report = loaded?.period === period ? loaded.data : undefined;
  return (
    <div className="max-w-4xl space-y-6 animate-rise-in">
      <div>
        <p className="text-xs uppercase tracking-widest text-[var(--v-muted-foreground)]">
          The story behind the figures
        </p>
        <h1 className="font-display mt-2 text-5xl">Reports.</h1>
        <p className="mt-3 text-sm">
          Daily, weekly, monthly and yearly views of the same sample scenario.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        {["daily", "weekly", "monthly", "yearly"].map((p) => (
          <button
            key={p}
            aria-pressed={p === period}
            onClick={() => setPeriod(p)}
            className={`rounded-lg border border-[var(--v-border)] px-4 py-2 text-sm capitalize ${p === period ? "bg-[var(--v-primary)] text-[var(--v-primary-foreground)]" : "bg-[var(--v-card)]"}`}
          >
            {p}
          </button>
        ))}
      </div>
      {loaded?.period === period && loaded.error ? (
        <p role="alert">
          Report could not load.{" "}
          <button className="underline" onClick={() => setRetry((v) => v + 1)}>
            Try again
          </button>
        </p>
      ) : !report ? (
        <p role="status">Preparing report…</p>
      ) : (
        <>
          <section className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-6">
            <p className="text-xs">
              {report.range} · {report.coverage_days} sample days available
            </p>
            <div className="my-6 grid gap-4 sm:grid-cols-3">
              {[
                ["Revenue", fmtKes(report.revenue)],
                ["Orders", report.orders],
                ["Average order", fmtKes(report.revenue / report.orders)],
              ].map(([k, v]) => (
                <div key={k}>
                  <p className="text-xs text-[var(--v-muted-foreground)]">
                    {k}
                  </p>
                  <p className="font-display mt-2 text-2xl">{v}</p>
                </div>
              ))}
            </div>
            <p className="text-sm leading-7">{report.report_text}</p>
            {report.top_items.length > 0 && (
              <table className="mt-6 w-full text-left text-sm">
                <caption className="mb-3 text-left font-semibold">
                  Today’s sample menu sales
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Dish</th>
                    <th scope="col">Units</th>
                    <th scope="col">Sales</th>
                  </tr>
                </thead>
                <tbody>
                  {report.top_items.map((r) => (
                    <tr key={r.name}>
                      <td className="py-3">{r.name}</td>
                      <td>{r.qty}</td>
                      <td>{fmtKes(r.sales_kes)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <button
              onClick={() => window.print()}
              className="mt-5 rounded-lg border border-[var(--v-border)] px-4 py-2 text-sm print:hidden"
            >
              Print / save report
            </button>
          </section>
          <DemoCreative key={period} topic="intelligence" period={period} />
        </>
      )}
    </div>
  );
}
