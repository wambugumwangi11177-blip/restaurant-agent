"use client";
import {useDailyReview} from '@/lib/owner/useDailyReview';
import {useEffect,useState} from 'react';
import Link from 'next/link';
import api from '@/lib/api';
import {kes} from '@/lib/owner/format';
import {useListQuery} from '@/lib/owner/useListQuery';
import StockItemDetail from '@/components/operations/StockItemDetail';

export const STOCK_TOOLS={
 'stock-value':'Stock valuation','recorded-waste':'Recorded waste','stock-movement':'Stock movement',
 'abc-counts':'ABC count schedule','supplier-prices':'Supplier price changes','expiry-risk':'Expiry risk',
} as const;
type Item={id:number;name:string;unit:string;current_stock:number;value_kes:number|null;cost_missing:boolean;negative_book_stock:boolean;needs_location_review?:boolean;velocity:string;spoilage_risk?:number;spoilage_window?:string|null;waste_pct:number;waste_qty_30d:number;abc_class:string;count_due:string;count_overdue:boolean;count_calendar?:string[]};
type Review={as_of?:string;entered_up_to?:string|null;value_kes:number|null;note:string;items:Item[];supplier_prices:{item:string;supplier:string;unit:string;first_kes:number;latest_kes:number;change_pct:number;deliveries:number}[]};
const unitPrice=(n:number)=>'KES '+n.toLocaleString('en-KE',{minimumFractionDigits:2,maximumFractionDigits:2});
const quantity=(n:number)=>Number(n.toFixed(3)).toLocaleString('en-KE');
export default function StockTool({view}:{view:keyof typeof STOCK_TOOLS}){
 const reviewDay=useDailyReview();
 const [data,setData]=useState<Review|null>(null),[error,setError]=useState(''),[retry,setRetry]=useState(0);
 const [search,setSearch]=useListQuery('q'),[page,setPage]=useListQuery('page','1'),[item,setItem]=useListQuery('item');
 useEffect(()=>{let active=true;api.get('/api/v1/owner/planning/stock-review').then(r=>{if(active)setData(r.data);}).catch(()=>{if(active)setError('Could not load the recorded stock data.');});return()=>{active=false;};},[retry,reviewDay]);
 const items=(data?.items??[]).filter(i=>i.name.toLowerCase().includes(search.toLowerCase())).filter(i=>view==='recorded-waste'?i.waste_qty_30d>0:view==='expiry-risk'?(i.spoilage_risk??0)>0:true);
 const prices=(data?.supplier_prices??[]).filter(p=>`${p.item} ${p.supplier}`.toLowerCase().includes(search.toLowerCase()));
 const total=view==='supplier-prices'?prices.length:items.length,pages=Math.max(1,Math.ceil(total/5)),current=Math.min(pages,Math.max(1,Number(page)||1));
 const rows=items.slice((current-1)*5,current*5);
 return <section aria-label={STOCK_TOOLS[view]} className="space-y-5">
  <h2 className="text-2xl font-semibold">{STOCK_TOOLS[view]}</h2>
  {error&&<p role="alert">{error} <button className="underline min-h-11" onClick={()=>setRetry(n=>n+1)}>Retry</button></p>}
  {!data&&!error&&<p role="status">Loading {STOCK_TOOLS[view].toLowerCase()}…</p>}
  {data&&<>
   <p className="text-sm text-[var(--v-muted-foreground)]">{view==='stock-value'?'Current book quantities and recorded unit costs':view==='supplier-prices'?'Delivered purchases · last 90 days':view==='abc-counts'?'Upcoming counts based on physical count history':'Recorded activity · last 30 calendar days'}. Checked {data.as_of?new Date(data.as_of+(/[zZ]|[+-]\d\d:\d\d$/.test(data.as_of)?'':'Z')).toLocaleString('en-KE',{timeZone:'Africa/Nairobi'}):'time unavailable'} Nairobi. Stock entries through {data.entered_up_to??'not recorded'}.</p>
   {view==='stock-value'&&<><p className="text-3xl font-semibold">{data.value_kes==null?'Unit costs needed':kes(data.value_kes)}</p><p className="text-sm">Book stock at current saved unit costs.</p><p className="text-sm">{data.items.filter(i=>i.cost_missing).length} items have no cost; {data.items.filter(i=>i.negative_book_stock).length} have negative recorded stock. Missing costs are excluded, and negative quantities contribute zero to this book value.</p></>}
   {view==='recorded-waste'&&<p className="text-sm">Recorded write-offs only. Quantities retain each item’s unit; they are not unexplained stock loss or expiry estimates.</p>}
   {view==='expiry-risk'&&<p className="text-sm">Estimated risk from movement and current stock, not confirmed spoilage or a known batch expiry. Unknown receipt dates remain unknown.</p>}
   <input className="daily-field" aria-label={`Search ${STOCK_TOOLS[view].toLowerCase()}`} value={search} onChange={e=>setSearch(e.target.value,true)} placeholder={view==='supplier-prices'?'Find an ingredient or supplier':'Find an ingredient'}/>
   {view==='supplier-prices'?<div className="space-y-3">{prices.slice((current-1)*5,current*5).map((p,i)=><article className="rounded-xl border p-4" key={i}><h3 className="font-semibold">{p.item} · {p.supplier}</h3><p>{unitPrice(p.first_kes)} → {unitPrice(p.latest_kes)} per {p.unit} · {p.change_pct.toFixed(1)}%</p><p className="text-sm">{p.deliveries} delivered purchases in the same unit</p></article>)}</div>:<div className="space-y-3">{rows.map(i=><article key={i.id} className="rounded-xl border p-4 space-y-2"><h3 className="font-semibold">{i.name}</h3>
    {view==='stock-value'&&<p>{quantity(i.current_stock)} {i.unit} · {i.cost_missing?'Unit cost missing':kes(i.value_kes)}{i.negative_book_stock?' · negative quantity needs reconciliation':''}</p>}
    {view==='recorded-waste'&&<p>{quantity(i.waste_qty_30d)} {i.unit} written off · {i.waste_pct.toFixed(1)}% of recorded stock out</p>}
    {view==='stock-movement'&&<p>Movement: {i.velocity||'Not enough history'} · {quantity(i.current_stock)} {i.unit} on hand</p>}
    {view==='abc-counts'&&<><p>Class {i.abc_class} · next count {i.count_due}{i.count_overdue?' · overdue':''}</p><p className="text-sm">Upcoming: {i.count_calendar?.join(', ')||'No additional dates calculated'}</p></>}
    {view==='expiry-risk'&&<p>Estimated risk {i.spoilage_risk?.toFixed(1)}% · {i.spoilage_window||'Expiry date unknown'}</p>}
    <button className="min-h-11 underline text-sm" onClick={()=>setItem(String(i.id))}>View supporting item records →</button>
   </article>)}</div>}
   {!total&&<p>No matching {view==='recorded-waste'?'recorded waste':view==='supplier-prices'?'supplier comparisons; two delivered purchases of the same item and unit are required':view==='expiry-risk'?'estimated expiry risks':'items'} for this view.</p>}
   <div className="flex justify-between items-center text-sm"><p>{total} records · page {current} of {pages}</p><div><button className="min-h-11 px-3 underline" disabled={current===1} onClick={()=>setPage(String(current-1))}>Previous</button><button className="min-h-11 px-3 underline" disabled={current===pages} onClick={()=>setPage(String(current+1))}>Next</button></div></div>
   {item&&data.items.some(i=>i.id===Number(item))&&<StockItemDetail id={Number(item)} key={item} onClose={()=>setItem('')} onSaved={()=>setRetry(n=>n+1)}/>}
   {view==='recorded-waste'&&<Link href="/entries?tool=waste" className="inline-flex min-h-11 underline">Record waste →</Link>}
  </>}
 </section>;
}
