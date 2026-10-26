"use client";
import {useContext,useState} from "react";
import PriceSimulator from "@/components/owner/PriceSimulator";
import Link from "next/link";
import Bars from "@/components/charts/Bars";
import BandForecast from "@/components/charts/BandForecast";
import HBars from "@/components/charts/HBars";
import Quadrant from "@/components/charts/Quadrant";
import { BLOCK_TITLES } from "@/lib/owner/blocks";
import { kes, kesShort, plural, shortDay, weekday } from "@/lib/owner/format";
import type { DeliveryBlock, DishesByKesBlock, ForecastBlock, InfoBlock, MatrixBlock, OutlookBlock, PriceIdeasBlock, SevenDayBlock, WinBackBlock } from "@/lib/owner/areaTypes";
import type { Area } from "@/lib/owner/types";
import { AreaFocus, BlockFrame, Empty, Grid, Note, Pill, Stat } from "./ui";

const T = BLOCK_TITLES.sales_dishes;

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
        <WhatIf block={b.simulator as InfoBlock} />
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
 const focus=useContext(AreaFocus);const unusual=focus==='unusual-sales-days';
 if(unusual)return <BlockFrame title="Unusual sales days" block={block}>{()=> <><p>Recorded sales compared with expected sales for the same day.</p>{block.unusual_days.length?block.unusual_days.map(u=><p key={u.date}>{shortDay(u.date)}: {kes(u.sales)} recorded against {kes(u.expected)} expected · {u.off_by_pct.toFixed(1)}%</p>):<p>No unusual sales days in this analysis window.</p>}<Note>{block.note}</Note></>}</BlockFrame>;

  return (
    <BlockFrame title={T.forecast} block={block}>{() => (<>
      <BandForecast label="Sales so far and the likely range for the next 7 days"
        actual={block.actual.map((a) => ({ date: a.date, sales: a.sales }))} next={block.next_7_days.map((n) => ({ date: n.date, usual: n.usual, low: n.low, high: n.high }))}
        unusual={(focus?[]:block.unusual_days).map((u) => ({ date: u.date, sales: u.sales, expected: u.expected }))} />
      <ul className="mt-2 grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px] text-[var(--v-muted-foreground)] sm:grid-cols-3">
        {block.next_7_days.map((n) => <li key={n.date} className="flex justify-between gap-2"><span>{n.day.slice(0, 3)}</span><span className="tabular-nums">{kesShort(n.low).replace("KES ", "")}–{kesShort(n.high).replace("KES ", "")}</span></li>)}
      </ul>
      {!focus&&block.unusual_days.length > 0 && <Note>Red dots: days that sold far from the usual — {block.unusual_days.map((u) => `${shortDay(u.date)} (${u.off_by_pct > 0 ? "+" : ""}${u.off_by_pct}%)`).join(", ")}.</Note>}
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
              <p className="mt-0.5 text-[11px] text-[var(--v-muted-foreground)]">{i.why}</p>
            </li>
          ))}
        </ul>
      )}
    </>)}</BlockFrame>
  );
}

function Delivery({ block }: { block: DeliveryBlock }) {
 const focus=useContext(AreaFocus),hours=focus==='best-and-weakest-hours';
 const [showGaps,setShowGaps]=useState(false);
 return <BlockFrame title={hours?'Best and weakest hours':T.delivery} block={hours?{...block,assumptions:[],assumption:undefined}:block}>{()=> <>
 {(!focus||!hours)&&<><p>Contribution after ingredients and recorded delivery commissions, by ordering channel.</p><HBars label="Share kept by channel" max={100} rows={block.channels.map(c=>({key:c.channel,label:c.channel,value:c.keeps_pct,valueLabel:`${c.keeps_pct.toFixed(1)}%`,note:`${plural(c.orders,'order')} · ${kes(c.keeps)} kept${c.pays_commission?' after commission':''}`}))}/>
 <h3 className="mt-4 font-semibold">Delivery dishes below your floor</h3>{block.delivery_gaps.length?block.delivery_gaps.slice(0,showGaps?undefined:5).map(g=><p className="py-2 text-sm" key={`${g.channel}-${g.dish}`}>{g.dish} on {g.channel}: keeps {kes(g.keeps)} a plate instead of {kes(g.keeps_dine_in)} in the restaurant ({g.commission_pct}% commission). It would need {kes(g.price_to_keep_floor)} to keep your floor.</p>):<p>No delivery dish falls below your configured margin floor.</p>}{block.delivery_gaps.length>5&&<><p className="text-sm">{block.delivery_gaps.length-5} more dishes lose too much to a delivery app.</p><button className="min-h-11 underline" onClick={()=>setShowGaps(v=>!v)}>{showGaps?"Show fewer":`Show all ${block.delivery_gaps.length} delivery findings`}</button></>}</>}
 {(!focus||hours)&&<><h3 className="font-semibold">Best and weakest hours</h3><p>Margin after ingredients by Nairobi time of day, before delivery commissions and other operating costs. This is a share of sales, not net profit.</p><HBars label="Share kept by time of day" max={100} rows={block.best_and_weakest_hours.map(h=>({key:h.hours,label:h.hours.charAt(0).toUpperCase()+h.hours.slice(1),value:h.keeps_pct,valueLabel:`${h.keeps_pct.toFixed(1)}%`,note:plural(h.orders,'order')}))}/></>}
 </>}</BlockFrame>;
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

function WhatIf({ block }: { block: InfoBlock }) {
  return (
    <BlockFrame title={T.simulator} block={block} quiet>{() => (<>
      <PriceSimulator/>
    </>)}</BlockFrame>
  );
}
