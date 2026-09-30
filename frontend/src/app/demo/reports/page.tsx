"use client";
// Reports: the owner's story pack. Everything on the page is also in the downloadable PDF
// (built by the same API from the same figures), so what they read is what they can share.
import { useEffect, useState } from "react";
import Link from "next/link";
import { Download, Printer } from "lucide-react";
import api from "@/lib/api";
import { fmtKes } from "@/lib/format";
import { Donut, LineSeries, WeekdayBars } from "@/components/demo/DemoCharts";

type Report = {
  period: string;
  range: string;
  revenue: number;
  orders: number;
  coverage_days: number;
  headline: string;
  kpis: { label: string; value: string }[];
  comparison: { label: string; previous_revenue: number; change_pct: number } | null;
  series: { date: string; day: string; revenue: number; orders: number }[];
  weekday_pattern: { day: string; revenue: number }[];
  channels: { label: string; value: number }[];
  dishes: { name: string; price: number; cost: number; units: number; sales: number; contribution: number; margin_pct: number }[];
  story: { title: string; text: string }[];
  decisions: { idea: string; why: string; next_step: string; expected: string | null }[];
  money_today: { sales: number; food_cost: number; contribution: number; labor: number; other: number; surplus: number };
  note: string;
};

const PERIODS = [
  ["daily", "Today"],
  ["weekly", "This week"],
  ["monthly", "This month"],
  ["yearly", "This year"],
] as const;

function Block({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <section className="break-inside-avoid">
      <h2 className="font-display text-xl">{title}</h2>
      {note && <p className="mb-3 mt-1 text-xs text-[var(--v-muted-foreground)]">{note}</p>}
      {children}
    </section>
  );
}

export default function DemoReports() {
  const [period, setPeriod] = useState<(typeof PERIODS)[number][0]>("daily");
  const [loaded, setLoaded] = useState<{ period: string; data?: Report; error?: boolean } | null>(null);
  const [retry, setRetry] = useState(0);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState(false);

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

  async function download() {
    setDownloading(true);
    setDownloadError(false);
    try {
      const r = await api.get<Blob>(`/api/v1/demo/reports/${period}/pdf`, { responseType: "blob", timeout: 60000 });
      const url = URL.createObjectURL(r.data);
      const link = document.createElement("a");
      link.href = url;
      link.download = `demo-restaurant-${period}-report.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch {
      setDownloadError(true);
    } finally {
      setDownloading(false);
    }
  }

  const money = report?.money_today;
  return (
    <div className="max-w-4xl space-y-6 animate-rise-in">
      <div className="print:hidden">
        <p className="text-xs uppercase tracking-widest text-[var(--v-muted-foreground)]">The story behind the figures</p>
        <h1 className="font-display mt-2 text-5xl">Reports.</h1>
        <p className="mt-3 text-sm">Pick a time, read the story in plain words, then download it as a PDF to share or keep.</p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <div className="flex flex-wrap gap-2">
          {PERIODS.map(([p, label]) => (
            <button
              key={p}
              aria-pressed={p === period}
              onClick={() => setPeriod(p)}
              className={`rounded-lg border border-[var(--v-border)] px-4 py-2 text-sm ${p === period ? "bg-[var(--v-primary)] text-[var(--v-primary-foreground)]" : "bg-[var(--v-card)]"}`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void download()}
            disabled={!report || downloading}
            className="inline-flex items-center gap-2 rounded-lg bg-[var(--v-primary)] px-4 py-2 text-sm font-semibold text-[var(--v-primary-foreground)] disabled:opacity-50"
          >
            <Download size={15} /> {downloading ? "Preparing PDF…" : "Download PDF"}
          </button>
          <button
            type="button"
            onClick={() => window.print()}
            disabled={!report}
            className="inline-flex items-center gap-2 rounded-lg border border-[var(--v-border)] bg-[var(--v-card)] px-4 py-2 text-sm disabled:opacity-50"
          >
            <Printer size={15} /> Print
          </button>
        </div>
      </div>
      {downloadError && (
        <p role="alert" className="text-xs print:hidden">
          The PDF could not be prepared just now. Please try again.
        </p>
      )}

      {loaded?.period === period && loaded.error ? (
        <p role="alert">
          The report could not load.{" "}
          <button className="underline" onClick={() => setRetry((v) => v + 1)}>
            Try again
          </button>
        </p>
      ) : !report ? (
        <p role="status">Preparing report…</p>
      ) : (
        <article className="space-y-8 rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-6 print:border-0 print:p-0">
          <header>
            <p className="text-xs text-[var(--v-muted-foreground)]">
              {report.range} · {report.coverage_days} sample {report.coverage_days === 1 ? "day" : "days"} available
            </p>
            <p className="font-display mt-2 text-2xl leading-snug">{report.headline}</p>
          </header>

          <div className="grid gap-3 sm:grid-cols-4">
            {report.kpis.map((k) => (
              <div key={k.label} className="rounded-lg bg-[hsl(42_40%_99%_/_0.7)] p-4">
                <p className="text-xs text-[var(--v-muted-foreground)]">{k.label}</p>
                <p className="font-display mt-2 text-xl">{k.value}</p>
              </div>
            ))}
          </div>
          {report.comparison && (
            <p className="-mt-4 text-xs text-[var(--v-muted-foreground)]">
              Sales are {report.comparison.change_pct >= 0 ? "up" : "down"} {Math.abs(report.comparison.change_pct)}% compared with {report.comparison.label} ({fmtKes(report.comparison.previous_revenue)}).
            </p>
          )}

          <Block title="How sales moved" note="A rising line means the restaurant is earning more. A dip is a quieter day worth understanding.">
            <LineSeries series={report.series} label="Sales over time" />
          </Block>

          <div className="grid gap-8 sm:grid-cols-2">
            <Block title="Which days are busiest" note="Average sales by weekday. The gold bar is your busiest day.">
              <WeekdayBars pattern={report.weekday_pattern} />
            </Block>
            <Block title="Where orders came from" note="How guests ordered today.">
              <Donut slices={report.channels} unit="count" />
            </Block>
          </div>

          <Block title="The story in plain words">
            <div className="space-y-4">
              {report.story.map((s) => (
                <p key={s.title} className="text-sm leading-7">
                  <b>{s.title}. </b>
                  {s.text}
                </p>
              ))}
            </div>
          </Block>

          {money && (
            <Block title="Where the money went" note="Contribution (sales minus ingredients) is not profit. Staff and running costs still come out of it.">
              <Donut
                slices={[
                  { label: "Ingredients", value: money.food_cost },
                  { label: "Staff", value: money.labor },
                  { label: "Other running costs", value: money.other },
                  { label: "What is left", value: money.surplus },
                ]}
              />
            </Block>
          )}

          {report.dishes.length > 0 && (
            <Block title="Your menu today" note="'Kept per plate' is the price minus what the ingredients cost.">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="text-xs text-[var(--v-muted-foreground)]">
                      <th scope="col" className="p-2 font-semibold">Dish</th>
                      <th scope="col" className="p-2 font-semibold">Price</th>
                      <th scope="col" className="p-2 font-semibold">Sold today</th>
                      <th scope="col" className="p-2 font-semibold">Sales</th>
                      <th scope="col" className="p-2 font-semibold">Kept per plate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.dishes.map((d) => (
                      <tr key={d.name} className="border-t border-[var(--v-border)]">
                        <td className="p-2 font-medium">{d.name}</td>
                        <td className="p-2">{fmtKes(d.price)}</td>
                        <td className="p-2">{d.units}</td>
                        <td className="p-2">{fmtKes(d.sales)}</td>
                        <td className="p-2">
                          {fmtKes(d.price - d.cost)} ({d.margin_pct}%)
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Block>
          )}

          {report.decisions.length > 0 && (
            <Block title="What we suggest" note="These are chances, not results. Nothing has been changed and nothing has been earned yet.">
              <div className="grid gap-3 sm:grid-cols-3">
                {report.decisions.map((d) => (
                  <div key={d.idea} className="rounded-lg border border-[var(--v-border)] p-4 text-xs leading-relaxed">
                    <p className="text-sm font-bold">{d.idea}</p>
                    <p className="mt-2">{d.why}</p>
                    <p className="mt-2">
                      <b>Next step: </b>
                      {d.next_step}
                    </p>
                    {d.expected && <p className="mt-2 font-semibold text-[var(--v-primary)]">{d.expected}</p>}
                  </div>
                ))}
              </div>
            </Block>
          )}

          {report.note && <p className="text-xs text-[var(--v-muted-foreground)]">{report.note}</p>}
          <p className="text-xs text-[var(--v-muted-foreground)] print:hidden">
            Want to go deeper?{" "}
            <Link href="/demo/os?topic=revenue&q=Why%20does%20revenue%20look%20like%20this%3F" className="font-semibold text-[var(--v-primary)]">
              Ask OS about these figures
            </Link>
          </p>
        </article>
      )}
    </div>
  );
}
