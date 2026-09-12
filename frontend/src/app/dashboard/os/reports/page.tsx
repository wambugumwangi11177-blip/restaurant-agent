"use client";
// Restaurant OS — REPORTS. Tracer build: Daily/Weekly/Monthly/Yearly tabs ->
// GET /api/v1/reports/{period} -> render drafted markdown report_text + numbers.
import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { fmtKes } from "@/lib/format";
import { OsLoading, OsEmpty, OsError } from "@/components/os/States";

type Report = {
  period: string; range: string; revenue: number; orders: number;
  top_items: { name: string; qty: number; sales_kes: number }[];
  report_text: string;
};

const TABS = ["daily", "weekly", "monthly", "yearly"] as const;

export default function OsReportsPage() {
  const [period, setPeriod] = useState<string>("daily");
  const [report, setReport] = useState<Report | null>(null);
  const [err, setErr] = useState(false);

  const load = useCallback((p: string) => {
    setErr(false); setReport(null);
    api.get<Report>(`/api/v1/reports/${p}`)
      .then((r) => setReport(r.data))
      .catch(() => setErr(true));
  }, []);
  useEffect(() => { load(period); }, [period, load]);

  return (
    <div className="max-w-3xl space-y-4">
      <section>
        <h1 className="text-2xl font-semibold">Reports</h1>
        <p className="text-sm text-[var(--muted-foreground)] mt-1">
          Drafted straight from your data — no estimates.
        </p>
      </section>

      <div className="inline-flex rounded-full border border-[var(--border)] overflow-hidden">
        {TABS.map((t) => (
          <button key={t} onClick={() => setPeriod(t)}
            className={`px-4 py-1.5 text-sm capitalize ${period === t ? "bg-[var(--accent)] text-white" : "text-[var(--muted-foreground)]"}`}>
            {t}
          </button>
        ))}
      </div>

      {err && <OsError message="Couldn't build the report right now." onRetry={() => load(period)} />}
      {!err && !report && <OsLoading rows={2} />}
      {!err && report && (
        <div className="rounded-2xl border border-[var(--border)] p-5">
          <p className="text-xs text-[var(--muted-foreground)]">{report.range}</p>
          <div className="flex gap-6 mt-2">
            <div>
              <p className="text-2xl font-semibold">{fmtKes(report.revenue)}</p>
              <p className="text-xs text-[var(--muted-foreground)]">Revenue</p>
            </div>
            <div>
              <p className="text-2xl font-semibold">{report.orders}</p>
              <p className="text-xs text-[var(--muted-foreground)]">Orders</p>
            </div>
          </div>
          {report.top_items.length > 0 && (
            <div className="mt-4">
              <p className="text-sm font-medium">Top sellers</p>
              {report.top_items.map((t) => (
                <p key={t.name} className="text-sm text-[var(--muted-foreground)] mt-1">
                  {t.name} — {t.qty} sold ({fmtKes(t.sales_kes)})
                </p>
              ))}
            </div>
          )}
          <hr className="my-4 border-[var(--border)]" />
          {/* Drafted report: whitespace-pre-wrap keeps the markdown structure readable */}
          <pre className="whitespace-pre-wrap text-sm font-sans">{report.report_text}</pre>
        </div>
      )}
      {!err && report && report.orders === 0 && (
        <OsEmpty message="This period has no sales yet." hint="Reports fill in automatically as orders come in." />
      )}
    </div>
  );
}