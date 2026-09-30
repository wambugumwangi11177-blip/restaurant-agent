"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import api from "@/lib/api";
import { DEMO_MODULES, field, recordRows, cell } from "@/lib/demo-modules";
import { RecordsTable, ValueChart } from "./DemoDataViews";
import DemoForecast from "./DemoForecast";

type View = {
  title: string;
  description: string;
  source: string;
  metrics: string[];
  mode: "trend" | "timeline" | "status" | "exceptions";
  visual: string;
  table: string;
  note: string;
};
export default function DemoAreaClient({
  areaKey,
  view,
}: {
  areaKey: string;
  view: View;
}) {
  const config = DEMO_MODULES[areaKey];
  const [data, setData] = useState<unknown>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">(
    config?.endpoint ? "loading" : "ready",
  );
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!config?.endpoint) return;
    let active = true;
    api
      .get(config.endpoint, { timeout: 20000 })
      .then((result) => {
        if (!active) return;
        if (result.data?.error || result.data?.available === false) {
          setState("error");
          return;
        }
        setData(result.data);
        setState("ready");
      })
      .catch(() => {
        if (active) setState("error");
      });
    return () => {
      active = false;
    };
  }, [config, reload]);
  const rows = recordRows(data, config?.rows).map((row) =>
    areaKey === "menu"
      ? {
          ...row,
          margin_pct:
            typeof row.cost_price === "number" && row.cost_price > 0
              ? row.margin_pct
              : "Verify item cost",
          classification:
            Number(row.qty_sold) > 0 ? row.classification : "No recorded sales",
        }
      : row,
  );
  const metrics: Record<string, unknown> =
    areaKey === "risk"
      ? {
          "Void spike flags": recordRows(data, ["void_spikes"]).length,
          "Refund velocity flags": recordRows(data, ["refund_velocity"]).length,
          "Payment mismatches": recordRows(data, ["payment_mismatches"]).length,
          "Off-hours events": recordRows(data, ["off_hours"]).length,
        }
      : areaKey === "data-trust"
        ? {
            "Items checked": field(data, "summary.total_items"),
            "Items with issues": field(data, "summary.items_with_issues"),
            "Missing costs": field(data, "summary.missing_cost_count"),
            "Cost coverage (%)": field(data, "summary.coverage_pct"),
          }
        : {};
  const chartKey =
    areaKey === "revenue" ? "revenue" : areaKey === "finance" ? "profit" : null;
  const chartLabel = areaKey === "revenue" ? "date" : "channel";
  return (
    <div className="animate-rise-in space-y-7">
      <Link
        href="/demo"
        className="inline-flex min-h-10 items-center gap-2 text-sm font-semibold text-[var(--v-primary)]"
      >
        <ArrowLeft size={16} /> Back to overview
      </Link>
      <header>
        <h1 className="font-display text-3xl font-semibold tracking-tight">
          {view.title}
        </h1>
        <p className="mt-2 text-base text-[var(--v-muted-foreground)]">
          {view.description}
        </p>
      </header>
      <p className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-4 text-sm text-[var(--v-muted-foreground)]">
        <strong className="block text-[var(--v-foreground)]">
          Recorded directly in this system
        </strong>
        <span className="mt-1 block">{config?.scope ?? view.source}</span>
      </p>
      {state === "loading" && (
        <p role="status">Loading recorded {view.title.toLowerCase()}…</p>
      )}
      {state === "error" && (
        <div
          role="alert"
          className="rounded-xl border border-[var(--v-border)] p-5"
        >
          <p>
            Could not load {view.title.toLowerCase()}. This does not mean there
            are no records.
          </p>
          <button
            type="button"
            className="mt-3 min-h-10 rounded-lg border border-[var(--v-border)] px-4 font-semibold"
            onClick={() => {
              setState("loading");
              setReload((n) => n + 1);
            }}
          >
            Try again
          </button>
        </div>
      )}
      {state === "ready" && (
        <>
          {Object.keys(metrics).length > 0 && data != null && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {Object.entries(metrics).map(([label, value]) => (
                <div
                  key={label}
                  className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-4"
                >
                  <p className="text-sm text-[var(--v-muted-foreground)]">
                    {label}
                  </p>
                  <p className="mt-2 text-2xl font-semibold">{cell(value)}</p>
                </div>
              ))}
            </div>
          )}
          {chartKey && rows.length > 0 && (
            <section className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5">
              <h2 className="mb-4 text-xl font-semibold">{view.visual}</h2>
              <ValueChart
                rows={rows}
                labelKey={chartLabel}
                valueKey={chartKey}
                title={view.visual}
                format={areaKey === "finance" ? "cents" : "money"}
              />
            </section>
          )}
          <section>
            <h2 className="mb-4 text-xl font-semibold">{view.table}</h2>
            <RecordsTable
              rows={rows}
              columns={config?.columns ?? []}
              caption={config?.scope ?? view.source}
              empty={config?.empty ?? "No records are available for this view."}
            />
          </section>
          {areaKey === "cash-reconciliation" && (
            <section>
              <h2 className="mb-4 text-xl font-semibold">
                M-Pesa settlement exceptions
              </h2>
              <RecordsTable
                rows={recordRows(data, ["mpesa_mismatches"])}
                columns={[
                  { key: "order_id", label: "Order" },
                  {
                    key: "total_cents",
                    label: "Recorded total",
                    format: "cents",
                  },
                  { key: "reason", label: "Reason" },
                ]}
                caption="Last 24 hours · recorded M-Pesa mismatches"
                empty="No M-Pesa mismatches were returned. This alone does not confirm that all payments have been reconciled."
              />
            </section>
          )}
        </>
      )}
      <DemoForecast area={areaKey} />
      <Link
        href={`/demo/os?q=${encodeURIComponent(`What should I review in ${view.title.toLowerCase()} and why?`)}`}
        className="inline-flex min-h-11 items-center rounded-lg bg-[var(--v-primary)] px-4 text-sm font-semibold text-[var(--v-primary-foreground)]"
      >
        Ask AI about {view.title.toLowerCase()}
      </Link>
    </div>
  );
}
