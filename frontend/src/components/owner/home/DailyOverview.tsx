"use client";
import Link from 'next/link';
import {kes,ago} from '@/lib/owner/format';
import type {OwnerHome} from '@/lib/owner/types';
export default function DailyOverview({home}:{home:OwnerHome}){
 const p=home.pulse;const pnl=home.areas.money.blocks.pnl as {lines?:{key:string;kes:number}[];period?:{label:string};state:string};
 const kept=pnl.lines?.find(l=>l.key==='kept')?.kes;
 const cash=p.money_match.cash;
 return <section aria-label="Daily overview"><p className="mb-3 text-xs text-[var(--v-muted-foreground)]">Records checked {ago(home.generated_at)} · sales {p.freshness.latest_sale_at?`last recorded ${ago(p.freshness.latest_sale_at)}`:"not recorded yet"}. Costs and cash have the periods shown below.</p><div className="grid gap-3 sm:grid-cols-3">{[
  {label:home.period==='today'?'Sales today':home.period==='7d'?'Sales · 7 calendar days':'Sales · 30 calendar days',value:kes(home.period==='today'?p.sales_today:p.sales_in_period),note:`${home.period==='today'?p.orders_today:p.orders_in_period} paid orders`,href:'/areas/sales_dishes?tool=sales-last-7-days'},
  {label:'Cash check · recorded shifts',value:cash.state==='no_data'?'Count needed':cash.to_check?`${cash.to_check} to review`:'Recorded counts match',note:'Review count windows and M-Pesa separately',href:'/areas/cash?tool=cash-count-check'},
  {label:'Recorded operating result',value:kes(kept),note:`${pnl.period?.label??'Calendar month so far'} · review costs and estimates`,href:'/areas/money?tool=profit-and-loss'}
 ].map(card=><Link key={card.label} href={card.href} className="rounded-2xl border border-[var(--v-border)] bg-white p-5"><p className="text-xs text-[var(--v-muted-foreground)]">{card.label}</p><p className="mt-2 text-2xl font-semibold">{card.value}</p><p className="mt-2 text-xs leading-relaxed text-[var(--v-muted-foreground)]">{card.note}</p></Link>)}</div></section>;
}
