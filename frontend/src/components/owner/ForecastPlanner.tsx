"use client";
import { useRef, useState } from 'react';
import Link from 'next/link';
import api from '@/lib/api';
type Dish={menu_item_id:number;dish:string;portions:number;low:number;high:number;has_recipe:boolean};
type Market={inventory_item_id:number;item:string;unit:string;need:number;on_hand:number;buffer:number;buy:number;supplier:string;supplier_id:number|null;cost_per_unit_cents:number};
const field='min-h-11 rounded-lg border p-2 bg-[var(--v-card)]';
const button='min-h-11 rounded-lg border px-4 py-2 font-semibold disabled:opacity-50';
export default function ForecastPlanner(){
 const [day,setDay]=useState(()=>new Date(Date.now()+86400000).toLocaleDateString('en-CA',{timeZone:'Africa/Nairobi'}));
 const [forecast,setForecast]=useState<{state:string;note:string;observed_days:string[];dishes:Dish[]}|null>(null);
 const [market,setMarket]=useState<Market[]>([]),[suppliers,setSuppliers]=useState<{id:number;name:string}[]>([]);
 const [message,setMessage]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const draftKey=useRef<string|null>(null);
 async function run(task:()=>Promise<void>){setBusy(true);setError('');setMessage('');try{await task();}catch(e){const x=e as {response?:{data?:{detail?:string}}};setError(typeof x.response?.data?.detail==='string'?x.response.data.detail:'Could not load this plan. Check your connection and retry.');}finally{setBusy(false);}}
 const planned=forecast?.dishes.filter(d=>d.has_recipe&&d.portions>0).map(d=>({menu_item_id:d.menu_item_id,portions:d.portions}))||[];
 return <section id="forecast-planner" className="space-y-4 rounded-xl border border-[var(--v-border)] p-4"><h2 className="text-xl font-semibold">Forecast → prep → supplier drafts</h2><p>Use matching weekdays, review portions, then turn raw ingredient needs into purchase drafts.</p>
 <label className="block">Planning date <input aria-label="Forecast planning date" type="date" className={field} value={day} disabled={busy} onChange={e=>{setDay(e.target.value);setForecast(null);setMarket([]);draftKey.current=null;}}/></label>
 <button className={button} disabled={busy} onClick={()=>run(async()=>{const [f,c]=await Promise.all([api.get(`/api/v1/owner/planning/forecast?on=${day}`),api.get('/api/v1/owner/operations/catalog')]);setForecast(f.data);setSuppliers(c.data.suppliers||[]);setMarket([]);draftKey.current=null;})}>Suggest portions from sales</button>
 {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
 {forecast&&<><p className="text-sm">{forecast.state.replaceAll('_',' ')} · Recorded comparison days: {forecast.observed_days.join(', ')||'None'}. {forecast.note}</p>
 {!forecast.dishes.length&&<p>No comparable sales yet. Use the manual recipe plan below.</p>}
 <div className="grid gap-3 sm:grid-cols-2">{forecast.dishes.map(d=><label className="flex items-center justify-between gap-3" key={d.menu_item_id}>{d.dish} · history {d.low}–{d.high}{!d.has_recipe&&' · Add recipe first'}<input aria-label={`${d.dish} forecast portions`} className={`${field} w-24`} type="number" min="0" max="10000" step="1" disabled={busy||!d.has_recipe} value={d.portions} onChange={e=>{setForecast({...forecast,dishes:forecast.dishes.map(x=>x.menu_item_id===d.menu_item_id?{...x,portions:Number(e.target.value)}:x)});setMarket([]);draftKey.current=null;}}/></label>)}</div>
 <button className={button} disabled={busy||!planned.length||planned.some(d=>!Number.isInteger(d.portions))} onClick={()=>run(async()=>{setMarket((await api.post('/api/v1/owner/planning/prep',{dishes:planned})).data.items);draftKey.current=null;})}>Accept portions & calculate market list</button></>}
 {!!market.length&&<><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{['Ingredient','Raw prep','On hand','Buffer','Buy','Supplier'].map(x=><th className="p-2" key={x}>{x}</th>)}</tr></thead><tbody>{market.map(m=><tr key={m.inventory_item_id}><th className="p-2">{m.item} ({m.unit})</th>{[m.need,m.on_hand,m.buffer,m.buy].map((v,n)=><td className="p-2" key={n}>{v}</td>)}<td className="p-2"><select aria-label={`${m.item} supplier`} className={field} value={m.supplier_id||''} disabled={busy||!m.buy} onChange={e=>{setMarket(market.map(x=>x.inventory_item_id===m.inventory_item_id?{...x,supplier_id:Number(e.target.value)||null}:x));draftKey.current=null;}}><option value="">Choose supplier</option>{suppliers.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select>{m.buy>0&&!m.cost_per_unit_cents&&<p>Enter unit cost in Inventory first.</p>}</td></tr>)}</tbody></table></div>
 <p>Drafts use the saved counting-unit costs and current stock. Purchasing groups them by supplier. Review and approve there before receiving.</p>
 <button className={button} disabled={busy||!market.some(m=>m.buy>0)||market.some(m=>m.buy>0&&(!m.supplier_id||!m.cost_per_unit_cents))} onClick={()=>run(async()=>{draftKey.current??=crypto.randomUUID();const r=await api.post('/api/v1/owner/planning/market-drafts',{dishes:planned,suppliers:Object.fromEntries(market.filter(m=>m.supplier_id).map(m=>[m.inventory_item_id,m.supplier_id])),entry_key:draftKey.current});setMessage(r.data.message);})}>Save supplier purchase drafts</button> <Link className="underline" href="/dashboard/purchasing">Review Purchasing →</Link></>}
 </section>;
}
