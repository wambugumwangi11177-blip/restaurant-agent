"use client";
/** One section of a report: its title, its state and the days it covers, a sentence made from its figures, the figures, and what they rest on. */
import Bars from "@/components/charts/Bars";
import StateChip from "@/components/owner/StateChip";
import { Assumptions, LABEL, Rows } from "@/components/owner/AnswerParts";
import { Pnl } from "@/components/owner/areas/MoneyArea";
import { kes, kesShort } from "@/lib/owner/format";
import type { PnlBlock } from "@/lib/owner/areaTypes";
import type { ReportPeriod, ReportSection } from "@/lib/owner/reportTypes";

export default function ReportSectionCard({ section, period }: { section: ReportSection; period: ReportPeriod }) {
  const empty = section.state === "no_data" || section.state === "unavailable";
  // The Profit & Loss is the same drawing Home has, with the accountant's file under it.
  if (section.key === "pnl" && period === "monthly" && !empty) return <Pnl block={section as unknown as PnlBlock} />;
  const series = section.series ?? [];
  const best = series.length ? Math.max(...series.map((m) => m.sales)) : 0;
  return (
    <section aria-label={section.title} className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-4 sm:p-5">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h2 className="font-display text-base font-semibold tracking-[-0.01em]">{section.title}</h2>
        {!section.info && <StateChip block={section} />}
        <span className={`${LABEL} ml-auto`}>{section.window}</span>
      </div>
      {empty ? (
        <p role="status" className="text-xs text-[var(--v-muted-foreground)]">{section.reason ?? "Nothing recorded yet."}</p>
      ) : (
        <div className="space-y-3">
          {section.headline && <p className="text-sm leading-relaxed">{section.headline}</p>}
          {series.length > 0 && (
            <Bars label="Sales by month, last 12 months" height={140} format={kesShort}
              bars={series.map((m) => ({ key: m.month, label: m.label.slice(0, 3), value: m.sales, highlight: m.sales === best,
                title: `${m.label}${m.partial ? " so far" : ""}: ${kes(m.sales)} · ${m.orders} orders` }))} />
          )}
          {section.rows.length > 0 && (series.length > 0
            ? <details><summary className="min-h-10 cursor-pointer py-2 text-[11px] font-bold">Month by month</summary><Rows rows={section.rows} /></details>
            : <Rows rows={section.rows} />)}
          <Assumptions items={section.assumptions} />
        </div>
      )}
    </section>
  );
}
