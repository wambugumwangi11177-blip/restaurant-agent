"use client";
// Vibanda Reports — Daily / Weekly / Monthly / Yearly. Deterministic numbers
// from /reports/{period}; LLM (OpenRouter) drafts the narrative when available,
// deterministic template stays as fallback so a report NEVER fails.
import { useCallback, useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { fmtKes } from "@/lib/format";
import { OsLoading, OsEmpty, OsError } from "@/components/os/States";
import SourceUnavailable from "@/components/vibanda/SourceUnavailable";

const observerMode = process.env.NEXT_PUBLIC_OBSERVER_MODE === "true";

type Report = {
  period: string; range: string; revenue: number; orders: number;
  top_items: { name: string; qty: number; sales_kes: number }[];
  report_text: string;
  llm_narrative?: string | null;
  llm_used?: boolean;
};

const TABS = ["daily", "weekly", "monthly", "yearly"] as const;

export default function VibandaReportsPage() {
  return observerMode ? <SourceUnavailable title="Reports" detail="Daily, weekly, monthly and yearly reports will be generated only after Macsoft periods and totals are reconciled." /> : <VibandaReportsContent />;
}

function VibandaReportsContent() {
  const [period, setPeriod] = useState<string>("daily");
  const [report, setReport] = useState<Report | null>(null);
  const [err, setErr] = useState(false);
  const requestId = useRef(0);

  const load = useCallback((p: string) => {
    const id = ++requestId.current;
    setErr(false); setReport(null);
    api.get<Report>(`/api/v1/reports/${p}`)
      .then((r) => { if (id === requestId.current) setReport(r.data); })
      .catch(() => { if (id === requestId.current) setErr(true); });
  }, []);
  useEffect(() => {
    // The request itself is the external synchronization performed here.
    // Loading/error state is deliberately reset by the request helper.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load(period);
    return () => { requestId.current += 1; };
  }, [period, load]);

  return (
    <div className="animate-rise-in max-w-4xl space-y-4">
      <div className="mb-2">
        <p className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--v-muted-foreground)]">Drafted from your data</p>
        <h1 className="font-display text-[clamp(2rem,4vw,3.25rem)] font-semibold leading-[1.02] tracking-[-0.045em]">
          Reports<span className="text-[var(--v-primary)]">.</span>
        </h1>
        <p className="mt-3 text-sm text-[var(--v-muted-foreground)]">Daily, weekly, monthly and yearly — real numbers, plainly explained.</p>
        <p className="mt-2 text-sm text-[var(--v-muted-foreground)]">Prototype data · Macsoft is not connected</p>
      </div>

      <div className="inline-flex rounded-lg border border-[var(--v-border)] bg-[hsl(42_40%_99_/_0.68)] p-1">
        {TABS.map((t) => (
          <button key={t} onClick={() => setPeriod(t)}
            className={`min-h-8 rounded-md px-4 text-[11px] font-bold capitalize transition-colors ${
              period === t ? "bg-[var(--v-primary)] text-[var(--v-primary-foreground)]" : "text-[var(--v-muted-foreground)]"
            }`}>
            {t}
          </button>
        ))}
      </div>

      {err && <OsError message="Couldn't build the report right now." onRetry={() => load(period)} />}
      {!err && !report && <OsLoading rows={2} />}
      {!err && report && (
        <div className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5">
          <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--v-muted-foreground)]">{report.period} · {report.range}</p>
          <div className="mt-3 grid gap-4 sm:grid-cols-3">
            <div>
              <p className="text-[10px] text-[var(--v-muted-foreground)]">Revenue</p>
              <p className="font-display mt-1 text-xl font-semibold">{fmtKes(report.revenue)}</p>
            </div>
            <div>
              <p className="text-[10px] text-[var(--v-muted-foreground)]">Orders</p>
              <p className="font-display mt-1 text-xl font-semibold">{report.orders}</p>
            </div>
            <div>
              <p className="text-[10px] text-[var(--v-muted-foreground)]">Avg order</p>
              <p className="font-display mt-1 text-xl font-semibold">
                {report.orders ? fmtKes(report.revenue / report.orders) : "—"}
              </p>
            </div>
          </div>

          {report.llm_narrative && (
            <div className="mt-5 rounded-xl bg-[hsl(42_71%_75_/_0.18)] p-4">
              <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-[hsl(208_29%_19_/_0.92)]">{report.llm_narrative}</p>
            </div>
          )}

          {report.top_items.length > 0 && (
            <div className="mt-5 border-t border-[var(--v-border)] pt-4">
              <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">Top sellers</p>
              {report.top_items.map((t) => (
                <div key={t.name} className="mt-2 flex items-center justify-between text-sm">
                  <span>{t.name}</span>
                  <span className="text-[var(--v-muted-foreground)]">{t.qty} sold · {fmtKes(t.sales_kes)}</span>
                </div>
              ))}
            </div>
          )}

          <details className="mt-5 border-t border-[var(--v-border)] pt-4">
            <summary className="cursor-pointer text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">
              Full data table
            </summary>
            <pre className="mt-3 whitespace-pre-wrap font-sans text-[12px] leading-relaxed text-[hsl(208_29%_19_/_0.82)]">{report.report_text}</pre>
          </details>

          {report.orders === 0 && (
            <OsEmpty message="No paid, non-cancelled orders are recorded for this period." hint="Macsoft is not connected, so these records do not establish the restaurant's actual sales or customer activity." />
          )}
        </div>
      )}
    </div>
  );
}
