"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import api from "@/lib/api";
import {
  cell,
  field,
  recordRows,
  DEMO_MODULES,
  type RecordRow,
} from "@/lib/demo-modules";
import { VIBANDA_AREA_SECTIONS } from "@/lib/vibandaAreas";
import { RecordsTable, ValueChart } from "./DemoDataViews";

type Source = { state: "loading" | "ready" | "error"; data?: unknown };
const SOURCES = {
  menu: "/api/v1/ai/menu-engineering?narrate=false",
  profit: "/api/v1/ai/profit?narrate=false",
  supply: "/api/v1/ai/supply-chain",
  quality: "/api/v1/ai/data-quality",
  roi: "/api/v1/ai/roi?narrate=false",
} as const;
type SourceKey = keyof typeof SOURCES;
type Feed = {
  period: string;
  performance: {
    revenue_trend: { date: string; revenue: number; orders: number }[];
  };
  orders: { split: Record<string, number> };
  stock: {
    recorded_items?: number;
    low_stock: { name: string; qty: number }[];
  };
};
function Panel({
  title,
  note,
  href,
  children,
}: {
  title: string;
  note: string;
  href: string;
  children: React.ReactNode;
}) {
  return (
    <section className="min-w-0 rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-display text-xl font-semibold">{title}</h3>
        <Link
          className="min-h-10 content-center text-sm font-semibold text-[var(--v-primary)]"
          href={href}
        >
          Open details
        </Link>
      </div>
      <p className="mb-5 text-sm leading-6 text-[var(--v-muted-foreground)]">
        {note}
      </p>
      {children}
    </section>
  );
}
export default function DemoOwnerInsights({ feed }: { feed: Feed }) {
  const [sources, setSources] = useState<Record<SourceKey, Source>>({
    menu: { state: "loading" },
    profit: { state: "loading" },
    supply: { state: "loading" },
    quality: { state: "loading" },
    roi: { state: "loading" },
  });
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    void Promise.allSettled(
      Object.entries(SOURCES).map(async ([key, endpoint]) => {
        try {
          const result = await api.get(endpoint, { timeout: 20000 });
          const failed = result.data?.error || result.data?.available === false;
          if (active)
            setSources((s) => ({
              ...s,
              [key]: {
                state: failed ? "error" : "ready",
                data: failed ? undefined : result.data,
              },
            }));
        } catch {
          if (active) setSources((s) => ({ ...s, [key]: { state: "error" } }));
        }
      }),
    );
    return () => {
      active = false;
    };
  }, [retry]);
  function status(key: SourceKey) {
    return sources[key].state === "loading" ? (
      <p role="status" className="text-sm">
        Loading recorded analysis…
      </p>
    ) : sources[key].state === "error" ? (
      <div role="alert" className="text-sm">
        <p>
          This analysis could not be loaded. Other sections remain available.
        </p>
        <button
          type="button"
          onClick={() => setRetry((n) => n + 1)}
          className="mt-2 min-h-10 font-semibold text-[var(--v-primary)]"
        >
          Retry analyses
        </button>
      </div>
    ) : null;
  }
  const trend = feed.performance.revenue_trend;
  const channels: RecordRow[] = Object.entries(feed.orders.split).map(
    ([channel, orders]) => ({ channel, orders }),
  );
  const menu = recordRows(sources.menu.data, ["matrix"])
    .slice(0, 10)
    .map((row) => ({
      ...row,
      margin_pct:
        typeof row.cost_price === "number" && row.cost_price > 0
          ? row.margin_pct
          : "Verify item cost",
      classification:
        Number(row.qty_sold) > 0 ? row.classification : "No recorded sales",
    }));
  const costsComplete =
    sources.quality.state === "ready" &&
    Number(field(sources.quality.data, "summary.total_items")) > 0 &&
    field(sources.quality.data, "summary.items_with_issues") === 0;
  const profitHasSales =
    Number(field(sources.profit.data, "summary.total_orders_30d")) > 0;
  return (
    <div className="space-y-8">
      <section aria-labelledby="owner-performance">
        <div className="mb-5">
          <h2
            id="owner-performance"
            className="font-display text-2xl font-semibold"
          >
            What is driving the business?
          </h2>
          <p className="mt-2 text-base text-[var(--v-muted-foreground)]">
            Sales, service and margin evidence to guide your next decision.
          </p>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel
            title="Sales over the last 7 days"
            note="Paid, non-cancelled orders · Nairobi calendar days · today is still in progress"
            href="/demo/revenue"
          >
            <ValueChart
              rows={trend}
              labelKey="date"
              valueKey="revenue"
              title="Daily paid revenue"
            />
            <details className="mt-5">
              <summary className="min-h-10 cursor-pointer text-sm font-semibold">
                View daily sales table
              </summary>
              <RecordsTable
                rows={trend}
                columns={DEMO_MODULES.revenue.columns}
                caption="Last 7 calendar days · KES"
                empty="No sales history is available."
              />
            </details>
          </Panel>
          <Panel
            title="Order volume"
            note="Paid, non-cancelled orders for the same 7 days · compare service volume with sales"
            href="/demo/orders"
          >
            <ValueChart
              rows={trend}
              labelKey="date"
              valueKey="orders"
              title="Daily paid orders"
              format="count"
            />
          </Panel>
          <Panel
            title="How guests are ordering"
            note={`Recorded order counts · ${feed.period} · includes all statuses and payment states, not revenue shares`}
            href="/demo/pos"
          >
            <ValueChart
              rows={channels}
              labelKey="channel"
              valueKey="orders"
              title="Order mix by channel"
              format="count"
            />
            <div className="mt-5">
              <RecordsTable
                rows={channels}
                columns={[
                  { key: "channel", label: "Channel" },
                  { key: "orders", label: "Orders" },
                ]}
                caption={`Channel mix · ${feed.period}`}
                empty="No channel records are available for this period."
              />
            </div>
          </Panel>
          <Panel
            title="Margin and cost confidence"
            note="Historical non-cancelled orders, including unpaid orders · modeled food costs, before operating expenses"
            href="/demo/finance"
          >
            {status("profit")}
            {sources.profit.state === "ready" &&
              (costsComplete && profitHasSales ? (
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-sm text-[var(--v-muted-foreground)]">
                      Modeled gross contribution
                    </p>
                    <p className="mt-2 text-2xl font-semibold tabular-nums">
                      {cell(
                        field(
                          sources.profit.data,
                          "summary.total_gross_profit_30d",
                        ),
                        "cents",
                      )}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-[var(--v-muted-foreground)]">
                      Modeled gross margin
                    </p>
                    <p className="mt-2 text-2xl font-semibold">
                      {cell(
                        field(sources.profit.data, "summary.gross_margin_pct"),
                        "percent",
                      )}
                    </p>
                  </div>
                  <p className="col-span-2 text-sm text-[var(--v-muted-foreground)]">
                    This is an estimate from item costs, not net profit or
                    verified savings.
                  </p>
                </div>
              ) : (
                <p className="text-sm leading-6">
                  {profitHasSales
                    ? "Verify menu costs before relying on a margin figure."
                    : "Record orders and verify menu costs before a margin figure is meaningful."}
                </p>
              ))}
            <div className="mt-5 border-t border-[var(--v-border)] pt-4">
              {status("quality")}
              {sources.quality.state === "ready" && (
                <>
                  <p className="text-sm">
                    {cell(field(sources.quality.data, "summary.total_items"))}{" "}
                    menu items checked ·{" "}
                    {cell(
                      field(sources.quality.data, "summary.items_with_issues"),
                    )}{" "}
                    cost issues
                  </p>
                  <Link
                    href="/demo/data-trust"
                    className="mt-2 inline-flex min-h-10 items-center text-sm font-semibold text-[var(--v-primary)]"
                  >
                    Review cost checks
                  </Link>
                </>
              )}
            </div>
          </Panel>
        </div>
      </section>
      <section aria-labelledby="owner-evidence">
        <h2
          id="owner-evidence"
          className="mb-5 font-display text-2xl font-semibold"
        >
          Where to focus next
        </h2>
        <div className="grid gap-4">
          <Panel
            title="Menu performance"
            note="Top 10 dishes by recorded sales · historical analysis window · item margin excludes operating costs"
            href="/demo/menu"
          >
            {status("menu")}
            {sources.menu.state === "ready" && (
              <RecordsTable
                rows={menu}
                columns={DEMO_MODULES.menu.columns}
                caption="Dish popularity and modeled item margin"
                empty="Record menu items, costs and sales to compare dish performance."
              />
            )}
          </Panel>
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel
              title="Ingredients at the reorder point"
              note="Current recorded quantities · check the physical stock before ordering"
              href="/demo/stock"
            >
              <RecordsTable
                rows={feed.stock.low_stock}
                columns={[
                  { key: "name", label: "Ingredient" },
                  { key: "qty", label: "Quantity remaining" },
                ]}
                caption="Items at or below their configured reorder threshold"
                empty={
                  feed.stock.recorded_items
                    ? "No recorded ingredients are below their threshold."
                    : "No inventory records are available. Add stock quantities and reorder thresholds."
                }
              />
            </Panel>
            <Panel
              title="Overdue supplier commitments"
              note="Sent purchase orders past their expected delivery date · contact the supplier before service is affected"
              href="/demo/purchasing"
            >
              {status("supply")}
              {sources.supply.state === "ready" && (
                <RecordsTable
                  rows={recordRows(sources.supply.data, ["overdue_orders"])}
                  columns={[
                    { key: "supplier", label: "Supplier" },
                    { key: "item", label: "Item" },
                    { key: "days_overdue", label: "Days overdue" },
                    { key: "total_cost", label: "Commitment", format: "cents" },
                  ]}
                  caption="Up to 10 overdue sent purchase orders"
                  empty={
                    Number(
                      field(sources.supply.data, "summary.total_suppliers"),
                    )
                      ? "No overdue sent purchase orders were returned."
                      : "No suppliers are configured. Add suppliers and delivery dates to monitor commitments."
                  }
                />
              )}
            </Panel>
          </div>
        </div>
      </section>
      <section
        aria-labelledby="owner-value"
        className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5"
      >
        <h2 id="owner-value" className="font-display text-2xl font-semibold">
          Value to review
        </h2>
        <p className="mt-2 text-sm leading-6 text-[var(--v-muted-foreground)]">
          Last 30 days · workload estimates and projected pricing impact, kept
          separate from realized savings.
        </p>
        <div className="mt-5">
          {status("roi")}
          {sources.roi.state === "ready" && (
            <>
              <div className="grid gap-4 sm:grid-cols-3">
                <div>
                  <p className="text-sm text-[var(--v-muted-foreground)]">
                    Estimated admin time avoided
                  </p>
                  <p className="mt-2 text-2xl font-semibold">
                    {cell(
                      field(sources.roi.data, "time_saved.hours_saved_30d"),
                    )}{" "}
                    hours
                  </p>
                  <p className="mt-2 text-sm">
                    Based on activity benchmarks, not measured staff hours.
                  </p>
                </div>
                <div>
                  <p className="text-sm text-[var(--v-muted-foreground)]">
                    Approved pricing decisions
                  </p>
                  <p className="mt-2 text-2xl font-semibold">
                    {cell(
                      field(
                        sources.roi.data,
                        "money_captured.recommendations_approved",
                      ),
                    )}
                  </p>
                  <p className="mt-2 text-sm">
                    Projected monthly impact:{" "}
                    {cell(
                      field(
                        sources.roi.data,
                        "money_captured.monthly_impact_cents",
                      ),
                      "cents",
                    )}
                    . Approval does not verify realized profit.
                  </p>
                </div>
                <div>
                  <p className="text-sm text-[var(--v-muted-foreground)]">
                    Opportunities to review
                  </p>
                  <p className="mt-2 text-2xl font-semibold">
                    {recordRows(sources.roi.data, ["opportunities"]).length}
                  </p>
                  <p className="mt-2 text-sm">
                    Potential benefits can overlap; they are not added together.
                  </p>
                </div>
              </div>
              <div className="mt-5">
                <RecordsTable
                  rows={recordRows(sources.roi.data, ["opportunities"])}
                  columns={[
                    { key: "label", label: "Opportunity" },
                    {
                      key: "monthly_value_cents",
                      label: "Estimated monthly value",
                      format: "cents",
                    },
                  ]}
                  caption="Unrealized estimates · review evidence before acting"
                  empty="No opportunity estimates were returned. This does not prove that every area has been evaluated."
                />
              </div>
            </>
          )}
        </div>
      </section>
      <section aria-labelledby="all-owner-modules">
        <h2
          id="all-owner-modules"
          className="font-display text-2xl font-semibold"
        >
          Your restaurant, area by area
        </h2>
        <p className="mt-2 text-base text-[var(--v-muted-foreground)]">
          Open the evidence behind a decision. Each page shows its records,
          scope and any missing source.
        </p>
        <div className="mt-5 space-y-6">
          {VIBANDA_AREA_SECTIONS.map((section) => (
            <div key={section.id}>
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-[var(--v-muted-foreground)]">
                {section.title}
              </h3>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {section.areas.map(([label, note, slug]) => (
                  <Link
                    key={slug}
                    href={`/demo/${slug}`}
                    className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-4 transition hover:border-[var(--v-primary)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--v-primary)]"
                  >
                    <p className="text-base font-semibold">{label}</p>
                    <p className="mt-2 text-sm leading-6 text-[var(--v-muted-foreground)]">
                      {note}
                    </p>
                    <p className="mt-3 text-sm font-semibold text-[var(--v-primary)]">
                      {DEMO_MODULES[slug]?.endpoint
                        ? "View recorded evidence"
                        : "Review source requirements"}
                    </p>
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-3">
          <Link
            href="/demo/os"
            className="min-h-11 rounded-lg border border-[var(--v-border)] px-4 py-3 text-sm font-semibold"
          >
            Ask AI about your restaurant
          </Link>
          <Link
            href="/demo/reports"
            className="min-h-11 rounded-lg border border-[var(--v-border)] px-4 py-3 text-sm font-semibold"
          >
            Open owner reports
          </Link>
          <Link
            href="/demo/support"
            className="min-h-11 rounded-lg border border-[var(--v-border)] px-4 py-3 text-sm font-semibold"
          >
            Support
          </Link>
        </div>
      </section>
    </div>
  );
}
