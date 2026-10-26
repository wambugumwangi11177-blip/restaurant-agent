"use client";
import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import api from "@/lib/api";
import { kes } from "@/lib/owner/format";

type Result = {
 state:string; dish:string; demand_change_pct:number; elasticity:number; sensitivity_source:string; confidence_pct:number;
 rows:{key:string;label:string;unit:string;before:number|null;after:number|null}[]; notes:string[];
};
export default function PriceSimulator() {
 const [items,setItems]=useState<{id:number;name:string;price_kes:number}[]>([]);
 const [dish,setDish]=useState(''),[price,setPrice]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [result,setResult]=useState<Result|null>(null);
 useEffect(()=>{let active=true;async function load(){try{const r=await api.get('/api/v1/owner/planning/menu-review');if(active)setItems(r?.data?.items??[]);}catch{if(active)setError('Could not load dishes. Reload to retry.');}}void load();return()=>{active=false;};},[]);
 async function calculate(e:FormEvent) {
  e.preventDefault();setBusy(true);setError('');setResult(null);
  try {const [whole,fraction='']=price.split('.');const r=await api.post('/api/v1/owner/planning/price-simulation',{menu_item_id:Number(dish),new_price_cents:Number(whole)*100+Number(fraction.padEnd(2,'0'))});setResult(r.data);}
  catch {setError('Could not model this price. Check the dish and price, then retry.');}
  finally {setBusy(false);}
 }
 const display=(value:number|null,unit:string)=>value===null?'Cost missing':unit==='kes'?kes(value):unit==='percent'?`${value}%`:String(value);
 return <div className="space-y-4">
  <p className="text-sm">Choose a dish and a proposed price. Compare its sales and contribution if demand responds. This does not save a price.</p>
  <form onSubmit={calculate} className="grid items-end gap-3 sm:grid-cols-[1fr_1fr_auto]">
   <label className="text-xs">Dish<select aria-label="Simulation dish" required value={dish} onChange={e=>{setDish(e.target.value);setPrice(String(items.find(i=>i.id===Number(e.target.value))?.price_kes??''));setResult(null);}} className="mt-1 min-h-11 w-full rounded-lg border border-[var(--v-border)] bg-white p-2"><option value="">Choose a dish</option>{items.map(i=><option key={i.id} value={i.id}>{i.name} · {kes(i.price_kes)}</option>)}</select></label>
   <label className="text-xs">Proposed price (KES)<input aria-label="Simulation proposed price" required inputMode="decimal" pattern={String.raw`[0-9]+(\.[0-9]{1,2})?`} value={price} onChange={e=>{setPrice(e.target.value);setResult(null);}} className="mt-1 min-h-11 w-full rounded-lg border border-[var(--v-border)] bg-white p-2"/></label>
   <button disabled={busy||!dish} className="leviii-primary-button">{busy?'Calculating…':'Model price & demand'}</button>
  </form>
  {error&&<p role="alert" className="text-sm text-[var(--v-destructive)]">{error}</p>}
  {result&&<div role="status" className="space-y-3"><h3 className="text-lg font-semibold">{result.dish} · 30-day scenario</h3><p className="text-sm">Projected portion change: {result.demand_change_pct}%. Price sensitivity: {result.elasticity} ({result.sensitivity_source}).</p><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th className="p-2">Measure</th><th className="p-2">Current price</th><th className="p-2">Proposed price</th></tr></thead><tbody>{result.rows.map(row=><tr key={row.key} className="border-t border-[var(--v-border)]"><th className="p-2">{row.label}</th><td className="p-2">{display(row.before,row.unit)}</td><td className="p-2">{display(row.after,row.unit)}</td></tr>)}</tbody></table></div>{result.notes.map(note=><p key={note} className="text-xs leading-relaxed text-[var(--v-muted-foreground)]">{note}</p>)}</div>}
  <Link href="/areas/money?tool=price-impact" className="inline-flex min-h-11 items-center text-xs font-semibold text-[var(--v-primary)]">Compare the full P&L with fixed portions →</Link>
 </div>;
}
