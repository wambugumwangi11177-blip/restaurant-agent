"use client";
// Reports — Daily (control) · Weekly (performance) · Monthly (the full Profit & Loss, with the accountant's file) · Yearly (trends).
// Every section is the block Home shows for the same thing, worked out by the owner API (/owner/report/{period}); the writing
// assistant's own take is a separate, optional note that is left out unless every number in it is backed.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { OsLoading, OsError } from "@/components/os/States";
import SourceUnavailable from "@/components/owner/SourceUnavailable";
import CreativeNote from "@/components/owner/CreativeNote";
import InsightNote from "@/components/owner/InsightNote";
import StateChip from "@/components/owner/StateChip";
import ReportSectionCard from "@/components/owner/reports/ReportSectionCard";
import { lastMonths } from "@/lib/owner/format";
import { tenantConfig } from "@/lib/tenantConfig";
import type { Insight } from "@/lib/owner/types";
import type { OwnerReport, ReportPeriod } from "@/lib/owner/reportTypes";

const observerMode = process.env.NEXT_PUBLIC_OBSERVER_MODE === "true";

type SourceConnection = {
  source: string;
  state: "receiving" | "awaiting_first_delivery" | "unavailable";
  records: number | null;
  last_received_at: string | null;
  reconciled: boolean;
};

const TABS: { id: ReportPeriod; label: string; hint: string }[] = [
  { id: "daily", label: "Daily", hint: "Did today go to plan?" },
  { id: "weekly", label: "Weekly", hint: "How did the week perform?" },
  { id: "monthly", label: "Monthly", hint: "The full Profit & Loss" },
  { id: "yearly", label: "Yearly", hint: "The trends" },
];

// Backend timestamps are naive UTC (see time_utils.py), so "Z" is what makes the browser read them correctly.
const fmtReceived = (iso: string) =>
  new Date(iso.endsWith("Z") ? iso : `${iso}Z`).toLocaleString("en-KE", {
    timeZone: "Africa/Nairobi", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  });

function sourceLine(conn: SourceConnection): string {
  if (conn.state === "unavailable")
    return "Macsoft delivery state unavailable — the source mirror could not be read";
  if (conn.state === "awaiting_first_delivery")
    return "Macsoft has not delivered any records yet — figures below come from data recorded in this system";
  const received = `Macsoft connected · ${conn.records?.toLocaleString("en-KE") ?? 0} record${conn.records === 1 ? "" : "s"} received`;
  const when = conn.last_received_at ? ` · last ${fmtReceived(conn.last_received_at)}` : "";
  // Delivered is not complete. Only a clean reconcile run proves the latter.
  const checked = conn.reconciled ? " · reconciled" : " · completeness not reconciled";
  return received + when + checked;
}

export default function ReportsPage() {
  return observerMode ? <SourceUnavailable title="Reports" detail="Daily, weekly, monthly and yearly reports will be generated only after Macsoft periods and totals are reconciled." /> : <ReportsContent />;
}

function ReportsContent() {
  const { user } = useAuth();
  const macsoft = tenantConfig(user?.tenant_name).source === "macsoft";
  const [period, setPeriod] = useState<ReportPeriod>("daily");
  const [month, setMonth] = useState<string | null>(null);        // null: the month so far
  const [report, setReport] = useState<OwnerReport | null>(null);
  const [insight, setInsight] = useState<Insight | null>(null);
  const [err, setErr] = useState(false);
  const [connection, setConnection] = useState<SourceConnection | null>(null);
  const requestId = useRef(0);
  const months = useMemo(() => lastMonths(), []);

  // Real delivery state, only for a restaurant whose figures are a mirror of its till.
  useEffect(() => {
    if (!macsoft) return;
    let active = true;
    api.get<{ data_provenance?: { source_connection?: SourceConnection } }>("/api/v1/overview/today", { timeout: 15000 })
      .then((r) => { const conn = r.data?.data_provenance?.source_connection; if (active && conn) setConnection(conn); })
      .catch(() => { /* Say nothing rather than guess at the source state. */ });
    return () => { active = false; };
  }, [macsoft]);

  const load = useCallback((p: ReportPeriod, m: string | null) => {
    const id = ++requestId.current;
    setErr(false); setReport(null); setInsight(null);
    api.get<OwnerReport>(`/api/v1/owner/report/${p}`, { params: p === "monthly" && m ? { month: m } : undefined })
      .then((r) => {
        if (id !== requestId.current) return;
        setReport(r.data);
        api.get<{ insight?: Insight | null }>(`/api/v1/owner/report/${p}/notes`, { params: p === "monthly" && m ? { month: m } : undefined })
          .then((note) => { if (id === requestId.current) setInsight(note.data?.insight ?? null); })
          .catch(() => { /* The report is already on screen. A missing note does not fail it. */ });
      })
      .catch(() => { if (id === requestId.current) setErr(true); });
  }, []);
  useEffect(() => {
    // The request itself is the external synchronization performed here.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load(period, month);
    return () => { requestId.current += 1; };
  }, [period, month, load]);

  const sales = report?.sections.find((s) => s.key === "sales");
  const hasOrders = !!sales && sales.state !== "no_data" && Number(sales.orders ?? 0) > 0;
  const isNow = period !== "monthly" || month === null || month === months[0].value;

  return (
    <div className="animate-rise-in max-w-4xl space-y-4">
      <div className="mb-2">
        <p className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--v-muted-foreground)]">Worked out from your records</p>
        <h1 className="font-display text-[clamp(2rem,4vw,3.25rem)] font-semibold leading-[1.02] tracking-[-0.045em]">
          Reports<span className="text-[var(--v-primary)]">.</span>
        </h1>
        <p className="mt-3 text-sm text-[var(--v-muted-foreground)]">Daily, weekly, monthly and yearly — the same figures as Home, in the order you read them.</p>
        {connection && <p className="mt-2 text-sm text-[var(--v-muted-foreground)]">{sourceLine(connection)}</p>}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div role="tablist" aria-label="Report" className="inline-flex rounded-lg border border-[var(--v-border)] bg-[hsl(42_40%_99_/_0.68)] p-1">
          {TABS.map((t) => (
            <button key={t.id} role="tab" aria-selected={period === t.id} title={t.hint} onClick={() => setPeriod(t.id)}
              className={`min-h-10 rounded-md px-4 text-[11px] font-bold transition-colors ${period === t.id ? "bg-[var(--v-primary)] text-[var(--v-primary-foreground)]" : "text-[var(--v-muted-foreground)]"}`}>
              {t.label}
            </button>
          ))}
        </div>
        {period === "monthly" && (
          <label className="flex items-center gap-2 text-[11px] font-bold">
            <span>Month</span>
            <select value={month ?? months[0].value} onChange={(e) => setMonth(e.target.value === months[0].value ? null : e.target.value)}
              className="min-h-10 rounded-lg border border-[var(--v-border)] bg-[var(--v-card)] px-2 text-xs font-semibold">
              {months.map((m, i) => <option key={m.value} value={m.value}>{m.label}{i === 0 ? " (so far)" : ""}</option>)}
            </select>
          </label>
        )}
      </div>

      {err && <OsError message="Couldn't build the report right now." onRetry={() => load(period, month)} />}
      {!err && !report && <OsLoading rows={2} />}
      {!err && report && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--v-muted-foreground)]">{report.period} · {report.range}</p>
            <StateChip block={report} />
          </div>
          {/* The assistant's own take, loaded separately so the report never waits on it; not asked for when there is nothing to take,
              nor for a month that is over (its evidence is the current one). */}
          {hasOrders && isNow && <CreativeNote endpoint={`/api/v1/reports/${report.period}/creative`} />}
          {report.state === "no_data" && (
            <p role="status" className="rounded-lg bg-[var(--v-muted)] px-3 py-2 text-xs text-[var(--v-muted-foreground)]">Nothing is recorded for this report yet. Each section below says what it is waiting for.</p>
          )}
          <div className="space-y-3">
            {report.sections.map((s) => <ReportSectionCard key={s.key} section={s} period={report.period} />)}
          </div>
          <InsightNote insight={insight} />
        </>
      )}
    </div>
  );
}
