"use client";
import Link from "next/link";
import { useState } from "react";
import Bars from "@/components/charts/Bars";
import BandForecast from "@/components/charts/BandForecast";
import HBars from "@/components/charts/HBars";
import Quadrant from "@/components/charts/Quadrant";
import { BLOCK_TITLES } from "@/lib/owner/blocks";
import { kes, kesShort, plural, shortDay, weekday } from "@/lib/owner/format";
import { monthGainCents } from "@/lib/menuMath";
import type { DeliveryBlock, DishesByKesBlock, ForecastBlock, InfoBlock, MatrixBlock, OutlookBlock, PriceIdeasBlock, SevenDayBlock, WinBackBlock } from "@/lib/owner/areaTypes";
import type { Area } from "@/lib/owner/types";
import { BlockFrame, Empty, Grid, Note, Pill, Stat } from "./ui";

const T = BLOCK_TITLES.sales_dishes;
const GAPS_SHOWN = 5;
const KINDS = ["Best dish", "Popular, earns little", "Earns well, few order it", "Consider removing"];

export default function SalesArea({ area }: { area: Area }) {
  const b = area.blocks;
  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-2">
        <SevenDay block={b.seven_day as SevenDayBlock} />
        <Forecast block={b.forecast as ForecastBlock} />
      </div>
      <Matrix block={b.matrix as MatrixBlock} />
      <div className="grid gap-3 md:grid-cols-2">
        <DishesByKes block={b.dishes_by_kes as DishesByKesBlock} />
        <PriceIdeas block={b.price_ideas as PriceIdeasBlock} />
      </div>
      <Delivery block={b.delivery as DeliveryBlock} />
      <div className="grid gap-3 md:grid-cols-3">
        <Outlook block={b.outlook as OutlookBlock} />
        <WinBack block={b.win_back as WinBackBlock} />
        <WhatIf block={b.simulator as InfoBlock} idea={(b.price_ideas as PriceIdeasBlock).ideas?.[0]} />
      </div>
    </div>
  );
}

function SevenDay({ block }: { block: SevenDayBlock }) {
  const best = block.days?.reduce((a, d) => (d.sales > a.sales ? d : a), block.days[0]);
  return (
    <BlockFrame title={T.seven_day} block={block}>{() => (<>
      <p className="mb-2 font-display text-xl font-semibold tracking-[-0.03em]">{kes(block.total)}</p>
      <Bars label="Sales for each of the last 7 days" format={kesShort}
        bars={block.days.map((d) => ({ key: d.date, label: weekday(d.date), value: d.sales, highlight: d.date === best?.date && d.sales > 0, title: `${weekday(d.date)} ${shortDay(d.date)}: ${kes(d.sales)} · ${plural(d.orders, "order")}` }))} />
    </>)}</BlockFrame>
  );
}

function Forecast({ block }: { block: ForecastBlock }) {
  return (
    <BlockFrame title={T.forecast} block={block}>{() => (<>
      <BandForecast label="Sales so far and the likely range for the next 7 days"
        actual={block.actual.map((a) => ({ date: a.date, sales: a.sales }))} next={block.next_7_days.map((n) => ({ date: n.date, usual: n.usual, low: n.low, high: n.high }))}
        unusual={block.unusual_days.map((u) => ({ date: u.date, sales: u.sales, expected: u.expected }))} />
      <ul className="mt-2 grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px] text-[var(--v-muted-foreground)] sm:grid-cols-3">
        {block.next_7_days.map((n) => <li key={n.date} className="flex justify-between gap-2"><span>{n.day.slice(0, 3)}</span><span className="tabular-nums">{kesShort(n.low).replace("KES ", "")}–{kesShort(n.high).replace("KES ", "")}</span></li>)}
      </ul>
      {block.unusual_days.length > 0 && <Note>Red dots: days that sold far from the usual — {block.unusual_days.map((u) => `${shortDay(u.date)} (${u.off_by_pct > 0 ? "+" : ""}${u.off_by_pct}%)`).join(", ")}.</Note>}
      <Note>{block.note}</Note>
    </>)}</BlockFrame>
  );
}

function Matrix({ block }: { block: MatrixBlock }) {
  const count = (k: string) => block.dishes?.filter((d) => d.kind === k).length ?? 0;
  return (
    <BlockFrame title={T.matrix} block={block}>{() => (<>
      <Quadrant label="Every dish by how much it sells and how much each plate earns you" popularLine={block.popular_line_units} earnsLine={block.earns_line}
        dishes={block.dishes.map((d) => ({ name: d.name, sold: d.sold, earns: d.earns_per_plate, kind: d.kind }))} />
      <ul className="mt-3 grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4">
        {KINDS.map((k) => <li key={k}><b className="tabular-nums">{count(k)}</b> <span className="text-[var(--v-muted-foreground)]">{k.toLowerCase()}</span></li>)}
      </ul>
    </>)}</BlockFrame>
  );
}

function DishesByKes({ block }: { block: DishesByKesBlock }) {
  return (
    <BlockFrame title={T.dishes_by_kes} block={block}>{() => (<>
      <HBars label="What each dish earns you, last 30 days" rows={block.dishes.map((d) => ({ key: d.name, label: d.name, value: d.profit, valueLabel: kes(d.profit), note: `${d.sold} sold · keeps ${d.keeps_pct}% of the price` }))} />
    </>)}</BlockFrame>
  );
}

function PriceIdeas({ block }: { block: PriceIdeasBlock }) {
  return (
    <BlockFrame title={T.price_ideas} block={block}>{() => (<>
      {block.ideas.length === 0 ? <Empty>No price looks wrong right now.</Empty> : (
        <ul className="space-y-3">
          {block.ideas.map((i) => (
            <li key={`${i.id}-${i.dish}`} className="text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2"><b>{i.dish}</b><Pill tone={i.kind === "Priced too low" ? "bad" : "quiet"}>{i.kind}</Pill></div>
              <p className="mt-0.5">{kes(i.from)} → <b>{kes(i.to)}</b> · about {kes(i.month_gain)} a month</p>
              <Bars label={`${i.dish} price now and the price that keeps your target`} height={88} bars={[
                { key: "now", label: "Now", value: i.from, title: `Now ${kes(i.from)}` },
                { key: "to", label: "Target", value: i.to, highlight: true, title: `Target ${kes(i.to)}` },
              ]} />
              <p className="mt-0.5 text-[11px] text-[var(--v-muted-foreground)]">{i.why}</p>
            </li>
          ))}
        </ul>
      )}
    </>)}</BlockFrame>
  );
}

function Delivery({ block }: { block: DeliveryBlock }) {
  return (
    <BlockFrame title={T.delivery} block={block}>{() => (<>
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <p className="mb-2 text-[11px] font-bold">What you keep of every KES 100, by where it was ordered</p>
          <HBars label="Share kept by channel" max={100} rows={block.channels.map((c) => ({ key: c.channel, label: c.channel, value: c.keeps_pct, valueLabel: `${c.keeps_pct}%`, note: `${plural(c.orders, "order")} · ${kes(c.keeps)} kept${c.pays_commission ? " after the app's commission" : ""}`, flag: c.pays_commission && c.keeps_pct < 40 }))} />
        </div>
        <div>
          <p className="mb-2 text-[11px] font-bold">Best and weakest hours</p>
          <HBars label="Share kept by time of day" max={100} rows={block.best_and_weakest_hours.map((h) => ({ key: h.hours, label: h.hours.charAt(0).toUpperCase() + h.hours.slice(1), value: h.keeps_pct, valueLabel: `${h.keeps_pct}%`, note: plural(h.orders, "order") }))} />
        </div>
      </div>
      {block.delivery_gaps.length > 0 && (
        <div className="mt-4">
          <p className="mb-1.5 text-[11px] font-bold">Dishes that lose too much to a delivery app</p>
          <HBars label="Less kept per plate than in the restaurant" rows={block.delivery_gaps.slice(0, GAPS_SHOWN).map((g) => ({ key: `${g.channel}-${g.dish}`, label: g.dish, value: Math.max(g.keeps_dine_in - g.keeps, 0), valueLabel: kes(g.keeps_dine_in - g.keeps), note: `${g.channel} keeps ${kes(g.keeps)}` }))} />
          <ul className="divide-y divide-[var(--v-border)] text-xs">
            {block.delivery_gaps.slice(0, GAPS_SHOWN).map((g) => (
              <li key={`${g.channel}-${g.dish}`} className="py-1.5">
                <b>{g.dish}</b> on {g.channel}: keeps {kes(g.keeps)} a plate instead of {kes(g.keeps_dine_in)} in the restaurant ({g.commission_pct}% commission). It would need {kes(g.price_to_keep_floor)} to keep your floor.
              </li>
            ))}
          </ul>
          {block.delivery_gaps.length > GAPS_SHOWN && <Note>{block.delivery_gaps.length - GAPS_SHOWN} more dishes lose too much to a delivery app. Ask LEVIII for the list.</Note>}
        </div>
      )}
    </>)}</BlockFrame>
  );
}

function Outlook({ block }: { block: OutlookBlock }) {
  return (
    <BlockFrame title={T.outlook} block={block}>{() => (<>
      <p className="font-display text-xl font-semibold tracking-[-0.03em]">{kes(block.next_30_days)}</p>
      <p className="text-xs text-[var(--v-muted-foreground)]">likely, between {kes(block.low)} and {kes(block.high)}</p>
      <Note>{block.note} We are {block.confidence_pct}% sure of the range.</Note>
    </>)}</BlockFrame>
  );
}

function WinBack({ block }: { block: WinBackBlock }) {
  return (
    <BlockFrame title={T.win_back} block={block}>{() => (<>
      <Grid cols={2}><Stat label="Regulars who stopped" value={block.lapsed_guests} /><Stat label="We can reach" value={block.reachable} note="they agreed to be contacted" /></Grid>
      <Link href="/os?q=Who%20should%20I%20win%20back%3F" className="mt-3 inline-flex min-h-10 items-center text-[11px] font-bold text-[var(--v-primary)]">Ask LEVIII how →</Link>
    </>)}</BlockFrame>
  );
}

function WhatIf({ block, idea }: { block: InfoBlock; idea?: PriceIdeasBlock["ideas"][number] }) {
  const [price, setPrice] = useState(idea?.to ?? 0);
  const plates = idea && idea.to !== idea.from ? Math.round((idea.month_gain * 100) / ((idea.to - idea.from) * 100)) : 0;
  const gain = idea ? monthGainCents(Math.round(idea.from * 100), Math.round(price * 100), plates) / 100 : 0;
  return (
    <BlockFrame title={T.simulator} block={block} quiet>{() => (<>
      <p className="text-xs leading-relaxed">{block.how}</p>
      {!idea ? <p className="mt-2 text-xs text-[var(--v-muted-foreground)]">When a dish has a price idea, you can slide the price and see the month change with no guesswork.</p> : (
        <div className="mt-3">
          <p className="text-xs font-semibold">{idea.dish}</p>
          <label className="mt-1 block text-[11px] text-[var(--v-muted-foreground)]">New price {kes(price)}
            <input className="mt-1 w-full" type="range" min={Math.max(1, Math.round(idea.from * 0.5))} max={Math.max(idea.to, idea.from) * 1.5} value={price} onChange={(e) => setPrice(Number(e.target.value))} />
          </label>
          <ul className="mt-2 grid grid-cols-3 gap-2 text-[11px]">
            <li><span className="block text-[var(--v-muted-foreground)]">Before</span><b>{kes(idea.from)}</b></li>
            <li><span className="block text-[var(--v-muted-foreground)]">After</span><b>{kes(price)}</b></li>
            <li><span className="block text-[var(--v-muted-foreground)]">Change a month</span><b>{kes(gain)}</b></li>
          </ul>
          <div className="mt-3 flex h-24 items-end gap-6" aria-label="Before and after">
            {[{ key: "before", label: "Before", value: idea.from }, { key: "after", label: "After", value: price }].map((bar) => {
              const top = Math.max(idea.from, price, 1);
              return (
                <div key={bar.key} className="flex w-16 flex-col items-center justify-end">
                  <span className="mb-1 text-[11px]">{kes(bar.value)}</span>
                  <div className="w-10 rounded-t bg-[var(--chart-bar,#e0b15a)]" style={{ height: `${Math.max(8, (bar.value / top) * 72)}px` }} />
                  <span className="mt-1 text-[11px]">{bar.label}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
      <Link href="/os?q=What%20if%20I%20raise%20the%20price%20of%20my%20best%20seller%3F" className="mt-3 inline-flex min-h-10 items-center text-[11px] font-bold text-[var(--v-primary)]">Try it →</Link>
    </>)}</BlockFrame>
  );
}
