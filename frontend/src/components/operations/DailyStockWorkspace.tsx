"use client";
import {useEffect,useState} from 'react';
import api from '@/lib/api';
import {useListQuery} from '@/lib/owner/useListQuery';
import StockItemDetail from './StockItemDetail';
type List={as_of:string;page:number;pages:number;total:number;items:{id:number;name:string;unit:string;on_hand:number;needs_location_review:boolean}[]};
export default function DailyStockWorkspace(){
 const [query,setQuery]=useListQuery('stockSearch'),[page,setPage]=useListQuery('page','1'),[selected,setSelected]=useListQuery('item');
 const [data,setData]=useState<List|null>(null),[error,setError]=useState(false),[retry,setRetry]=useState(0);
 useEffect(()=>{let active=true;api.get('/api/v1/daily/stock',{params:{q:query,page:Math.max(1,Math.floor(Number(page)||1))}}).then(r=>{if(active){setData(r.data);setError(false);}}).catch(()=>{if(active)setError(true);});return()=>{active=false;};},[query,page,retry]);
 return <div className="space-y-5 text-[#20362c]"><header><p className="text-xs text-[#596c61]">Ingredients & stock</p><h1 className="mt-1 text-2xl font-semibold">Count where it is. Record what happened.</h1><p className="mt-2 text-sm">Choose an item to count the store or kitchen, record waste, or review its handovers and receipt dates.</p></header>
 <input className="daily-field" aria-label="Find stock to record" placeholder="Find an ingredient…" value={query} onChange={e=>setQuery(e.target.value,true)}/>
 {error&&<p role="alert">Could not read stock records. <button className="min-h-11 underline" onClick={()=>setRetry(n=>n+1)}>Retry stock</button></p>}{!data&&!error&&<p role="status">Reading this branch’s stock…</p>}
 {data&&<><p className="text-xs text-[#596c61]">Checked {new Date(data.as_of).toLocaleString('en-KE',{timeZone:'Africa/Nairobi',dateStyle:'medium',timeStyle:'short'})} Nairobi · {data.total} items · page {data.page} of {data.pages}</p><div className="space-y-3">{data.items.map(i=><article key={i.id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[#dce2da] bg-white p-4"><div><h2 className="font-semibold">{i.name}</h2><p className="mt-1 text-sm">{Number(i.on_hand.toFixed(3))} {i.unit} recorded overall</p>{i.needs_location_review&&<p className="mt-1 text-xs text-amber-900">Location records need review before a clean close.</p>}</div><button className="min-h-11 rounded-xl bg-[#285744] px-4 text-sm font-semibold text-white" onClick={()=>setSelected(String(i.id))}>Count or record waste →</button></article>)}</div>{!data.items.length&&<p>No matching stock item in this branch.</p>}<div className="flex gap-4"><button disabled={data.page<=1} className="min-h-11 underline" onClick={()=>setPage(String(data.page-1))}>Previous</button><button disabled={data.page>=data.pages} className="min-h-11 underline" onClick={()=>setPage(String(data.page+1))}>Next</button></div></>}
 {selected&&/^\d+$/.test(selected)&&<StockItemDetail key={selected} id={Number(selected)} onSaved={()=>setRetry(n=>n+1)} onClose={()=>{setSelected('');setRetry(n=>n+1);}}/>}
 </div>;
}
