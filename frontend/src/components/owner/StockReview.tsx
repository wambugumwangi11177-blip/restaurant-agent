"use client";
import { useEffect, useState } from 'react';
import Link from 'next/link';
import api from '@/lib/api';
import Bars from '@/components/charts/Bars';
import { kes } from '@/lib/owner/format';

type Review = {value_kes:number;note:string;items:{id:number;name:string;unit:string;current_stock:number;value_kes:number;cost_missing:boolean;negative_book_stock:boolean;velocity:string;waste_pct:number;waste_qty_30d:number;abc_class:string;count_due:string;count_overdue:boolean;count_calendar?:string[]}[];supplier_prices:{item:string;supplier:string;unit:string;first_kes:number;latest_kes:number;change_pct:number;deliveries:number}[]};
export default function StockReview(){
 const [data,setData]=useState<Review|null>(null),[error,setError]=useState(false);
 useEffect(()=>{api.get('/api/v1/owner/planning/stock-review').then(r=>setData(r.data)).catch(()=>setError(true));},[]);
 return <section id="stock-review" className="space-y-4 rounded-xl border border-[var(--v-border)] p-4"><h2 className="text-xl font-semibold">Stock value & counting plan</h2>
 {error&&<p role="alert">Could not load stock review. Reload to retry.</p>}
 {!data&&!error&&<p>Loading stock review…</p>}
 {data&&<><p className="text-2xl font-semibold">Book stock: {kes(data.value_kes)}</p><p className="text-sm">{data.note}</p>
 {data.items.length>0&&<Bars label="Stock value by item" bars={data.items.slice(0,8).map(i=>({key:String(i.id),label:i.abc_class||i.name.slice(0,6),value:i.value_kes,title:`${i.name} · class ${i.abc_class}: ${i.cost_missing?'cost missing':kes(i.value_kes)}`}))}/>}
 <details><summary className="min-h-10 cursor-pointer text-[11px] font-bold text-[var(--v-primary)]">Show numbers</summary>
 <div className="overflow-x-auto"><table className="w-full text-left text-sm"><caption className="py-2 text-left">Recorded stock, waste and suggested next counts</caption><thead><tr>{['Item','On hand','Value','Waste / stock out','Movement','Class','Next count'].map(x=><th className="p-2" key={x}>{x}</th>)}</tr></thead><tbody>{data.items.map(i=><tr key={i.id}><th className="p-2">{i.name}</th><td className="p-2">{i.current_stock} {i.unit}{i.negative_book_stock&&' — reconcile negative stock'}</td><td className="p-2">{i.cost_missing?'Cost missing':kes(i.value_kes)}</td><td className="p-2">{i.waste_pct}% ({i.waste_qty_30d} {i.unit})</td><td className="p-2">{i.velocity}</td><td className="p-2">{i.abc_class}</td><td className="p-2">{i.count_due}{i.count_overdue?' · Due':''}</td></tr>)}</tbody></table></div></details>
 {!data.items.length&&<p>Add stock items to start a counting plan.</p>}
 <Link href="/dashboard/inventory" className="inline-flex min-h-11 items-center underline">Open inventory to record a count or waste →</Link>
 <h3 className="text-lg font-semibold">Next 30 days: counting calendar</h3><ul className="space-y-2">{data.items.map(i=><li key={i.id}><b>{i.name} · {i.abc_class}</b>: {i.count_calendar?.join(', ')||i.count_due}</li>)}</ul>
 <h3 className="text-lg font-semibold">Supplier price changes</h3>
 {!data.supplier_prices.length?<p>Two delivered purchases for the same supplier, item and unit are needed for a comparison.</p>:<div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{['Item / supplier','Unit','First price','Latest price','Change','Deliveries'].map(x=><th key={x} className="p-2">{x}</th>)}</tr></thead><tbody>{data.supplier_prices.map((p,n)=><tr key={n}><th className="p-2">{p.item} · {p.supplier}</th><td className="p-2">{p.unit}</td><td className="p-2">{kes(p.first_kes)}</td><td className="p-2">{kes(p.latest_kes)}</td><td className="p-2">{p.change_pct}%</td><td className="p-2">{p.deliveries}</td></tr>)}</tbody></table></div>}</>}
 </section>;
}
