"use client";

/* The forecast endpoints intentionally expose several heterogeneous, source-specific
 * payloads. The runtime guards below only render fields that are present. */
/* eslint-disable @typescript-eslint/no-explicit-any */

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { ArrowUpRight, CalendarDays, Sparkles, TriangleAlert } from "lucide-react";
import api from "@/lib/api";
import { getErrorMessage } from "@/lib/errors";
import { formatKES } from "@/lib/format";
import { isVerifiedVibandaSource } from "@/lib/vibandaSource";

type Area = "revenue" | "orders" | "stock" | "bookings" | "team" | "menu" | "finance" | "suppliers" | "purchasing" | "pos" | "kitchen" | "intelligence";
type SourceConnection = { state?: string; records?: number | null; reconciled?: boolean };
type ForecastState = "checking" | "waiting" | "loading" | "ready" | "empty" | "error" | "not-applicable";
type ForecastPayload = Record<string, any>;

const endpoints: Partial<Record<Area, string>> = {
  revenue: "/ai/revenue-forecast",
  orders: "/ai/revenue-forecast",
  stock: "/ai/inventory-predictions",
  bookings: "/ai/reservation-insights",
  team: "/ai/labor",
  menu: "/ai/menu-engineering",
  finance: "/ai/profit",
  suppliers: "/ai/supply-chain",
  purchasing: "/ai/supply-chain",
  pos: "/ai/revenue-forecast",
  kitchen: "/ai/kds-intelligence",
  intelligence: "/ai/forecast/twin?horizon=30",
};

function hasForecast(payload: ForecastPayload, area: Area) {
  if (area === "revenue" || area === "orders" || area === "pos") return (payload.forecast?.length ?? 0) > 0 || (payload.revenue_by_type?.length ?? 0) > 0;
  if (area === "stock") return (payload.predictions?.length ?? 0) > 0;
  if (area === "bookings") return (payload.peak_windows?.length ?? 0) > 0 || (payload.recommendations?.length ?? 0) > 0;
  if (area === "finance") return (payload.profit_forecast?.["7_day_forecast"]?.length ?? 0) > 0;
  if (area === "team") return (payload.recommendations?.length ?? 0) > 0 || (payload.daily_breakdown?.length ?? 0) > 0;
  if (area === "menu") return (payload.recommendations?.length ?? 0) > 0 || (payload.summary?.rising_items ?? 0) > 0 || (payload.summary?.falling_items ?? 0) > 0;
  if (area === "suppliers" || area === "purchasing") return (payload.recommendations?.length ?? 0) > 0 || (payload.overdue_orders?.length ?? 0) > 0;
  if (area === "kitchen") return (payload.rush_periods?.length ?? 0) > 0 || (payload.recommendations?.length ?? 0) > 0;
  return payload.available === true && Boolean(payload.summary);
}

function money(value: unknown) { return typeof value === "number" ? formatKES(value) : "—"; }

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return <section className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5"><div className="mb-4 flex items-center gap-2"><Sparkles size={16} className="text-[var(--v-primary)]"/><h2 className="font-display text-xl font-semibold">{title}</h2></div>{children}</section>;
}

function EmptyForecast({ message }: { message: string }) {
  return <p className="rounded-lg border border-dashed border-[var(--v-border)] p-4 text-sm text-[var(--v-muted-foreground)]">{message}</p>;
}

function ForecastContent({ area, data }: { area: Area; data: ForecastPayload }) {
  if (area === "revenue" || area === "orders") {
    const rows = (data.forecast ?? []).slice(0, 7);
    return <Panel title={area === "orders" ? "Expected sales activity" : "Expected revenue"}>{rows.length ? <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">{rows.map((row: any) => <div key={row.date} className="rounded-lg border border-[var(--v-border)] p-3"><p className="text-xs text-[var(--v-muted-foreground)]">{row.day}</p><p className="mt-1 font-semibold">{money(row.predicted_revenue)}</p><p className="mt-1 text-xs text-[var(--v-muted-foreground)]">Range {money(row.confidence_low)}–{money(row.confidence_high)}</p><p className="mt-1 text-xs text-[var(--v-muted-foreground)]">Confidence {row.confidence_pct ?? "—"}%</p></div>)}</div> : <EmptyForecast message="There is not enough verified sales history to calculate a forecast yet."/>}</Panel>;
  }

  if (area === "pos") {
    const rows = data.revenue_by_type ?? [];
    return <Panel title="Sales channel mix">{rows.length ? <div className="space-y-2">{rows.slice(0, 6).map((row: any, index: number) => <div key={String(row.type ?? row.order_type ?? index)} className="flex items-center justify-between rounded-lg border border-[var(--v-border)] p-3 text-sm"><span>{String(row.type ?? row.order_type ?? "Channel")}</span><span className="font-semibold">{money(row.revenue)}</span></div>)}</div> : <EmptyForecast message="Channel performance will appear after verified sales history is available."/>}</Panel>;
  }

  if (area === "stock") {
    const rows = (data.predictions ?? []).filter((row: any) => row.depletion_date || row.status !== "ok").slice(0, 8);
    return <Panel title="What may run out next">{rows.length ? <div className="space-y-2">{rows.map((row: any) => <div key={row.id ?? row.name} className="flex items-center justify-between gap-3 rounded-lg border border-[var(--v-border)] p-3 text-sm"><div><p className="font-medium">{row.name}</p><p className="text-xs text-[var(--v-muted-foreground)]">{row.status} · {row.days_until_depletion != null ? `${row.days_until_depletion} days of cover` : "depletion date unavailable"}</p></div><span className="text-right text-xs text-[var(--v-muted-foreground)]">{row.depletion_date ?? "—"}<br/>{row.optimal_order_qty != null ? `Order ${row.optimal_order_qty} ${row.unit}` : ""}</span></div>)}</div> : <EmptyForecast message="No verified stock depletion forecast is available yet."/>}</Panel>;
  }

  if (area === "finance") {
    const rows = (data.profit_forecast?.["7_day_forecast"] ?? []).slice(0, 7);
    return <Panel title="Expected profit">{rows.length ? <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">{rows.map((row: any) => <div key={row.date} className="rounded-lg border border-[var(--v-border)] p-3"><p className="text-xs text-[var(--v-muted-foreground)]">{row.day}</p><p className="mt-1 font-semibold">{money(row.projected_profit)}</p><p className="mt-1 text-xs text-[var(--v-muted-foreground)]">Range {money(row.profit_low)}–{money(row.profit_high)}</p></div>)}</div> : <EmptyForecast message="Profit projection needs enough verified sales and cost history before it can be shown."/>}</Panel>;
  }

  if (area === "intelligence") {
    const summary = data.summary;
    return <Panel title="Forward view">{summary ? <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><div><p className="text-xs text-[var(--v-muted-foreground)]">Baseline</p><p className="mt-1 font-semibold">{money(summary.baseline_revenue_cents)}</p></div><div><p className="text-xs text-[var(--v-muted-foreground)]">Projected</p><p className="mt-1 font-semibold">{money(summary.projected_revenue_cents)}</p></div><div><p className="text-xs text-[var(--v-muted-foreground)]">Expected change</p><p className="mt-1 font-semibold">{summary.uplift_pct != null ? `${summary.uplift_pct}%` : "—"}</p></div><div><p className="text-xs text-[var(--v-muted-foreground)]">Confidence</p><p className="mt-1 font-semibold">{summary.confidence_pct != null ? `${summary.confidence_pct}%` : "—"}</p></div></div> : <EmptyForecast message="The forward view needs verified sales history before it can be calculated."/>}</Panel>;
  }

  const recommendations = data.recommendations ?? [];
  const rows = area === "bookings" ? (data.peak_windows ?? []).slice(0, 6) : area === "kitchen" ? (data.rush_periods ?? []).filter((row: any) => row.is_rush).slice(0, 6) : area === "suppliers" || area === "purchasing" ? (data.overdue_orders ?? []).slice(0, 6) : [];
  const title = area === "bookings" ? "Demand patterns and booking guidance" : area === "kitchen" ? "Busy-period patterns" : area === "team" ? "Labor guidance" : area === "menu" ? "Menu movement to watch" : "Supplier and purchasing risks";
  return <Panel title={title}>{rows.length ? <div className="space-y-2">{rows.map((row: any, index: number) => <div key={row.date ?? row.label ?? row.id ?? index} className="flex items-center justify-between rounded-lg border border-[var(--v-border)] p-3 text-sm"><span>{row.label ?? row.date ?? row.supplier ?? row.item ?? "Upcoming period"}</span><span className="text-right text-xs text-[var(--v-muted-foreground)]">{row.load_factor ? `${row.load_factor}× normal load` : row.expected_at ?? row.days_overdue ? `${row.days_overdue ?? 0} days overdue` : "Review recommended"}</span></div>)}</div> : recommendations.length ? <div className="space-y-2">{recommendations.slice(0, 5).map((row: any, index: number) => <div key={row.id ?? index} className="rounded-lg border border-[var(--v-border)] p-3 text-sm"><p>{row.message ?? "A decision needs review."}</p>{row.action && <p className="mt-1 text-xs text-[var(--v-muted-foreground)]">Next step: {String(row.action).replace(/_/g, " ")}</p>}</div>)}</div> : <EmptyForecast message="No forward-looking owner guidance is available from the verified records yet."/>}</Panel>;
}

export default function VibandaForecast({ area, sourceVerified }: { area: string; sourceVerified?: boolean }) {
  const [state, setState] = useState<ForecastState>("checking");
  const [data, setData] = useState<ForecastPayload | null>(null);
  const [message, setMessage] = useState("");
  const load = useCallback(async () => {
    const endpoint = endpoints[area as Area];
    if (!endpoint) { setState("not-applicable"); return; }
    setState("checking"); setData(null); setMessage("");
    try {
      if (sourceVerified === false) { setState("waiting"); return; }
      if (sourceVerified !== true) {
        const source = await api.get<{ data_provenance?: { source_connection?: SourceConnection } }>("/api/v1/overview/today?period=today", { timeout: 15000 });
        if (!isVerifiedVibandaSource(source.data?.data_provenance?.source_connection)) { setState("waiting"); return; }
      }
      setState("loading");
      const result = await api.get<ForecastPayload>(endpoint, { timeout: 20000 });
      if (result.data?.available === false) { setMessage(result.data.error || "This forward view is not available yet."); setState("error"); return; }
      setData(result.data);
      setState(hasForecast(result.data, area as Area) ? "ready" : "empty");
    } catch (error) {
      setMessage(getErrorMessage(error, "The forward view could not be loaded."));
      setState("error");
    }
  }, [area, sourceVerified]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);
  if (state === "not-applicable" || state === "waiting" || state === "checking") return null;
  if (state === "loading") return <div className="rounded-xl border border-dashed border-[var(--v-border)] p-5 text-sm text-[var(--v-muted-foreground)]">Preparing the owner’s forward view from verified records…</div>;
  if (state === "error") return <div className="flex items-start justify-between gap-4 rounded-xl border border-[var(--v-border)] p-5"><div className="flex gap-3"><TriangleAlert size={18} className="mt-0.5 text-[var(--v-primary)]"/><p className="text-sm text-[var(--v-muted-foreground)]">{message}</p></div><button type="button" onClick={() => void load()} className="shrink-0 text-xs font-semibold text-[var(--v-primary)]">Try again</button></div>;
  if (!data || state === "empty") return <div className="rounded-xl border border-dashed border-[var(--v-border)] p-5 text-sm text-[var(--v-muted-foreground)]">Verified records are present, but there is not enough history for a reliable forward view yet.</div>;
  const forwardArea = ["revenue", "orders", "stock", "finance", "intelligence"].includes(area);
  return <div className="space-y-4"><div className="flex items-center gap-2 text-xs text-[var(--v-muted-foreground)]"><CalendarDays size={14}/><span>{forwardArea ? "Forward view from verified restaurant history" : "Owner insight from verified restaurant history"}</span><ArrowUpRight size={13} className="ml-auto text-[var(--v-primary)]"/></div><ForecastContent area={area as Area} data={data}/></div>;
}
