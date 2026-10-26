"use client";
import Bars, { type Bar } from "@/components/charts/Bars";
import StateChip from "@/components/owner/StateChip";
import { ago, kes, kesShort, nairobiTime, plural, shortDay, signedPct, weekday } from "@/lib/owner/format";
import type { BreakEven, Pulse as PulseData, OwnerHome } from "@/lib/owner/types";

const PERIOD_WORDS: Record<OwnerHome["period"], string> = { today: "Sales today", "7d": "Sales, last 7 days", "30d": "Sales, last 30 days" };

/** Zone 1 — the pulse: how today is going, against what the restaurant has to cover. */
export default function Pulse({ pulse, period }: { pulse: PulseData; period: OwnerHome["period"] }) {
  const todayShown = period === "today";
  const sales = todayShown ? pulse.sales_today : pulse.sales_in_period;
  const orders = todayShown ? pulse.orders_today : pulse.orders_in_period;
  const vs = pulse.vs_same_weekday_pct;
  const bars: Bar[] = pulse.trend_7d.map((d) => ({
    key: d.date, label: weekday(d.date), value: d.sales,
    title: `${weekday(d.date)} ${shortDay(d.date)}: ${kes(d.sales)} · ${plural(d.orders, "order")}`,
  }));
  const best = bars.reduce((a, b) => (b.value > a.value ? b : a), bars[0] ?? { value: 0, key: "" });
  bars.forEach((b) => { b.highlight = b.value > 0 && b.key === best.key; });

  return (
    <section aria-label="Today's pulse" className="leviii-pulse grid gap-4 lg:grid-cols-[1.1fr_1fr_1fr]">
      <div className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">{PERIOD_WORDS[period]}</p>
          <StateChip block={pulse} />
        </div>
        <p data-testid="sales-today" className="font-display mt-2 text-[2.1rem] font-semibold leading-none tracking-[-0.04em]">{kes(sales)}</p>
        <p className="mt-2 text-xs text-[var(--v-muted-foreground)]">{plural(orders, "paid order")}</p>
        {todayShown && (
          <p className="mt-3 text-sm">
            {vs != null
              ? <><b className={vs >= 0 ? "text-[var(--v-good)]" : "text-[var(--v-destructive)]"}>{signedPct(vs)}</b> <span className="text-[var(--v-muted-foreground)]">against the same time last {new Intl.DateTimeFormat("en-KE", { weekday: "long", timeZone: "Africa/Nairobi" }).format(new Date())}</span></>
              : <span className="text-[var(--v-muted-foreground)]">Compared with last week once there is a week of sales to compare.</span>}
          </p>
        )}
        <Freshness pulse={pulse} />
      </div>

      <div className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5">
        <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">The last 7 days</p><p className="mb-3 text-[10px] text-[var(--v-muted-foreground)]">Including today, up to now</p>
        <Bars bars={bars} label="Sales for each of the last 7 days" format={kesShort} state={pulse.trend_7d.some((d) => d.sales > 0) ? undefined : "no_data"} reason="No sales recorded in the last 7 days." />
      </div>

      <div className="grid gap-3 rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5">
        <CostsCovered be={pulse.breakeven_at} />
        <Match label="Cash count check" block={pulse.money_match.cash}
          text={pulse.money_match.cash.state === "no_data" || pulse.money_match.cash.state === "unavailable" ? pulse.money_match.cash.reason ?? "" :
            `${plural((pulse.money_match.cash.checked as number) ?? 0, "shift")} checked · ${(pulse.money_match.cash.to_check as number) ? `${pulse.money_match.cash.to_check} to look at` : "all match"}`} />
        <Match label="M-Pesa check" block={pulse.money_match.mpesa} text={pulse.money_match.mpesa.headline ?? pulse.money_match.mpesa.reason ?? ""} />
      </div>
    </section>
  );
}

function Freshness({ pulse }: { pulse: PulseData }) {
  const f = pulse.freshness;
  if (!f.latest_sale_at) return <p className="mt-3 text-[11px] text-[var(--v-muted-foreground)]">No sale recorded yet.</p>;
  return (
    <p className={`mt-3 text-[11px] ${f.is_stale ? "text-[var(--v-warn)]" : "text-[var(--v-muted-foreground)]"}`}>
      Latest sale {nairobiTime(f.latest_sale_at)} · {ago(f.latest_sale_at)}{f.is_stale ? " — the till may not be sending sales" : ""}
    </p>
  );
}

function CostsCovered({ be }: { be: BreakEven | PulseData["breakeven_at"] }) {
  if (be.state === "no_data" || be.state === "unavailable") {
    return (
      <div>
        <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">Costs covered</p>
        <p className="mt-1 text-xs text-[var(--v-muted-foreground)]">{be.reason}</p>
      </div>
    );
  }
  const share = be.break_even_kes > 0 ? Math.min(1, be.sales_today_kes / be.break_even_kes) : 0;
  return (
    <div>
      <div className="flex items-center gap-2">
        <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">Costs covered</p>
        <StateChip block={be} />
      </div>
      <p className="mt-1 text-sm font-semibold">
        {be.covered ? `Covered at ${be.crossed_at}` : `${kes(be.to_go_kes)} to go`}
      </p>
      <div role="progressbar" aria-label="Today's sales against what today has to cover" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(share * 100)}
        className="mt-2 h-2 overflow-hidden rounded-full bg-[var(--v-muted)]">
        <div className={`h-full rounded-full ${be.covered ? "bg-[var(--v-good)]" : "bg-[var(--v-primary)]"}`} style={{ width: `${share * 100}%` }} />
      </div>
      <p className="mt-1 text-[11px] text-[var(--v-muted-foreground)]">{kes(be.sales_today_kes)} of {kes(be.break_even_kes)} a day</p>
    </div>
  );
}

function Match({ label, block, text }: { label: string; block: PulseData["money_match"]["cash"]; text: string }) {
  return (
    <div>
      <div className="flex items-center gap-2">
        <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">{label}</p>
        <StateChip block={block} />
      </div>
      <p className="mt-1 text-xs text-[var(--v-muted-foreground)]">{text}</p>
    </div>
  );
}
