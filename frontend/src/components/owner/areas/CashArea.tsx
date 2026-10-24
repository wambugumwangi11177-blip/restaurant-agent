"use client";
import CheckMatrix from "@/components/charts/CheckMatrix";
import HBars from "@/components/charts/HBars";
import HeatGrid from "@/components/charts/HeatGrid";
import ShiftTable from "@/components/charts/ShiftTable";
import TenderMix from "@/components/charts/TenderMix";
import ThreeWayMatch, { leg } from "@/components/charts/ThreeWayMatch";
import ToleranceCurve from "@/components/charts/ToleranceCurve";
import { BLOCK_TITLES } from "@/lib/owner/blocks";
import { kes, nairobiTime, shortDay, toDate, weekday } from "@/lib/owner/format";
import type { BelowMenuPriceBlock, CancelledBlock, MpesaBlock, PatternsBlock, ShiftsBlock } from "@/lib/owner/areaTypes";
import type { Area } from "@/lib/owner/types";
import MpesaUpload from "./MpesaUpload";
import { BlockFrame, Empty, Grid, Note, Pill, Stat } from "./ui";

const T = BLOCK_TITLES.cash;

export default function CashArea({ area }: { area: Area }) {
  const b = area.blocks;
  return (
    <div className="space-y-3">
      <Shifts block={b.shifts as ShiftsBlock} cancelled={(b.cancelled_sales as CancelledBlock).cancelled_last_7_days} pricedUnder={(b.below_menu_price as BelowMenuPriceBlock).dishes?.length} />
      <div className="grid gap-3 md:grid-cols-2">
        <Cancelled block={b.cancelled_sales as CancelledBlock} />
        <BelowMenu block={b.below_menu_price as BelowMenuPriceBlock} />
      </div>
      <Patterns block={b.patterns as PatternsBlock} />
      <Mpesa block={b.mpesa as MpesaBlock} />
    </div>
  );
}

function sinceWhen(iso: string) {
  const local = new Date(toDate(iso).getTime() + 3 * 3600_000).toISOString().slice(0, 10);
  return `${weekday(local)} ${shortDay(local)}, ${nairobiTime(iso)}`;
}

/** The statement against the M-Pesa sales: the sentence, what was checked, then the two kinds of gap. The upload is always here: with no statement, it is the whole panel. */
function Mpesa({ block }: { block: MpesaBlock }) {
  return (
    <div className="space-y-3">
      <BlockFrame title={T.mpesa} block={block}>{() => {
        const sales = block.sales_without_payment!, pays = block.payments_without_sale!, matched = block.matched!, checked = block.checked!;
        const moreSales = sales.count - (sales.items?.length ?? 0), morePays = pays.count - (pays.items?.length ?? 0);
        return (<>
          <p className="text-sm leading-relaxed">{block.headline}</p>
          <div className="mt-3"><Grid cols={3}>
            <Stat label="Sales checked" value={checked.sales} note={`${checked.payments} payments on the statement`} />
            <Stat label="Matched" value={matched.sales} note={kes(matched.kes)} />
            <Stat label="To look at" value={sales.count + pays.count + (block.different_amounts?.length ?? 0)} note="sales or payments with no match" />
          </Grid></div>
          {sales.count > 0 && (
            <div className="mt-3"><p className="mb-1 text-[11px] font-bold">Sales with no payment on the statement · {kes(sales.kes)}</p>
              <ul className="space-y-1 text-xs">{sales.items!.map((s) => <li key={s.order_id} className="flex justify-between gap-3"><span>{sinceWhen(s.at)} · {s.what}</span><b className="shrink-0">{kes(s.kes)}</b></li>)}</ul>
              {moreSales > 0 && <Note>and {moreSales} more</Note>}
            </div>
          )}
          {pays.count > 0 && (
            <div className="mt-3"><p className="mb-1 text-[11px] font-bold">Payments with no sale recorded · {kes(pays.kes)}</p>
              <ul className="space-y-1 text-xs">{pays.items!.map((p) => <li key={p.receipt} className="flex justify-between gap-3"><span>{sinceWhen(p.at)} · {p.from || p.receipt}</span><b className="shrink-0">{kes(p.kes)}</b></li>)}</ul>
              {morePays > 0 && <Note>and {morePays} more</Note>}
            </div>
          )}
          {(block.different_amounts?.length ?? 0) > 0 && (
            <div className="mt-3"><p className="mb-1 text-[11px] font-bold">Paid a different amount from the one recorded</p>
              <ul className="space-y-1 text-xs">{block.different_amounts!.map((d) => <li key={d.receipt}>{d.receipt}: recorded {kes(d.sale_kes)}, paid {kes(d.payment_kes)}</li>)}</ul>
            </div>
          )}
          {block.outside_statement && block.outside_statement.sales > 0 && (
            <Note>{block.outside_statement.sales} M-Pesa sales ({kes(block.outside_statement.kes)}) fall outside the days this statement covers, so they are not checked.</Note>
          )}
          <Note>{block.note}</Note>
        </>);
      }}</BlockFrame>
      <MpesaUpload />
    </div>
  );
}

function Shifts({ block, cancelled, pricedUnder }: { block: ShiftsBlock; cancelled?: number; pricedUnder?: number }) {
  const day = (iso: string) => { const d = toDate(iso); const local = new Date(d.getTime() + 3 * 3600_000).toISOString().slice(0, 10); return `${weekday(local)} ${shortDay(local)}, ${nairobiTime(iso)}`; };
  const latest = block.shifts?.[0];
  const legs = latest ? [leg("cash", "Cash", latest.counted, latest.expected, latest.check)].filter((x) => x != null) : [];
  if (latest?.mpesa_gap != null) {
    const mpesa = leg("mpesa", "M-Pesa", 0, latest.mpesa_gap, latest.mpesa_gap > 0);
    if (mpesa) legs.push({ ...mpesa, left: "On the statement", right: kes(latest.mpesa_gap) + " not matched", gap: kes(latest.mpesa_gap), look: latest.mpesa_gap > 0 });
  }
  return (
    <div className="space-y-3">
      <BlockFrame title="How the money came in" block={{ ...block, state: (block.tenders?.length ? block.state === "no_data" ? "live" : block.state : "no_data") as ShiftsBlock["state"], reason: "Paid sales today will split into cash, M-Pesa and card once an order is taken." }}>{() => (
        <TenderMix tenders={block.tenders ?? []} />
      )}</BlockFrame>
      <BlockFrame title={T.shifts} block={block}>{() => (<>
        <ShiftTable label="Each cash count against what the till says" rows={(block.shifts ?? []).map((s) => ({ key: s.from, when: day(s.from), expected: s.expected, counted: s.counted, gap: s.gap, check: s.check, mpesaGap: s.mpesa_gap, cancelled: s.cancelled, stockGap: s.stock_gap, signal: s.signal }))} />
        <Note>A difference smaller than what you accept is not flagged.</Note>
      </>)}</BlockFrame>
      {block.state !== "no_data" && block.state !== "unavailable" && block.state !== "learning" && (
        <div className="space-y-3">
          <div className="grid gap-4 lg:grid-cols-2">
            <ThreeWayMatch legs={legs} />
            <ToleranceCurve toleranceKes={block.tolerance?.kes ?? 0} tolerancePct={block.tolerance?.pct ?? 0} dots={(block.shifts ?? []).map((s) => ({ key: s.from, expected: s.expected, gap: s.gap, label: day(s.from) }))} />
          </div>
          <div>
            <p className="mb-1 text-[11px] font-bold">The trick a count catches</p>
            {latest?.check
              ? <p className="text-xs">The latest count was {kes(Math.abs(latest.gap))} {latest.gap < 0 ? "short" : "over"}. A short drawer with no cancelled sale and no M-Pesa gap is the usual trick: cash taken and the sale left off, or the sale rung and the cash kept.</p>
              : <p className="text-xs text-[var(--v-muted-foreground)]">When a count sits outside what you accept, this names the trick that count is built to catch. Nothing is outside the line right now.</p>}
          </div>
          <CheckMatrix counts={{ cash: (block.shifts ?? []).filter((s) => s.check).length, cancelled: cancelled ?? 0, mpesa: (block.shifts ?? []).filter((s) => (s.mpesa_gap ?? 0) > 0).length, price: pricedUnder ?? 0, stock: (block.shifts ?? []).filter((s) => (s.stock_gap ?? 0) > 0).length }} />
        </div>
      )}
    </div>
  );
}

function Cancelled({ block }: { block: CancelledBlock }) {
  return (
    <BlockFrame title={T.cancelled_sales} block={block}>{() => (<>
      <Grid cols={2}>
        <Stat label="Cancelled, last 7 days" value={block.cancelled_last_7_days} />
        <Stat label="To look at" value={block.to_check} note={block.to_check ? "unusual cancelling, refunds or late-night activity" : "nothing unusual"} />
      </Grid>
      <Note>{block.note}</Note>
    </>)}</BlockFrame>
  );
}

function BelowMenu({ block }: { block: BelowMenuPriceBlock }) {
  return (
    <BlockFrame title={T.below_menu_price} block={block}>{() => (<>
      {block.dishes.length === 0 ? <Empty>Every dish was charged its menu price.</Empty> : (<>
        <HBars label="What charging under the menu price costs in a month" rows={block.dishes.map((d) => ({ key: d.dish, label: d.dish, value: d.month_loss, valueLabel: kes(d.month_loss), note: `Menu ${kes(d.menu_price)}, charged ${kes(d.charged)}` }))} />
        <ul className="mt-3 space-y-2.5 text-xs">
          {block.dishes.map((d) => (
            <li key={d.dish}><div className="flex justify-between gap-3"><b>{d.dish}</b><Pill tone="warn">{d.below_pct}% under</Pill></div><p className="text-[var(--v-muted-foreground)]">Menu {kes(d.menu_price)}, charged {kes(d.charged)} — about {kes(d.month_loss)} a month. A reason to check the till, not a finding about anyone.</p></li>
          ))}
        </ul>
      </>)}
    </>)}</BlockFrame>
  );
}

function Patterns({ block }: { block: PatternsBlock }) {
  return (
    <BlockFrame title={T.patterns} block={block}>{() => (<>
      <HeatGrid label="Shifts that came up short again and again" cells={block.patterns.map((p) => ({ weekday: p.weekday, shift: p.shift, timesShort: p.times_short, ofLast: p.of_last, title: `${p.when}: short ${p.times_short} of the last ${p.of_last}` }))} />
      {block.patterns.length === 0
        ? <Note>{String(block.reason ?? "No shift has come up short again and again.")}</Note>
        : <ul className="mt-3 space-y-1 text-xs">{block.patterns.map((p) => <li key={p.when}><b>{p.when}</b>: short {p.times_short} of the last {p.of_last} times, about {kes(p.short_each)} each — {kes(p.total)} in all.</li>)}</ul>}
      <Note>{block.note}</Note>
    </>)}</BlockFrame>
  );
}
