"use client";
import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import api from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { isOwnerAccount } from '@/lib/tenantHome';
import { pendingEntries, PendingEntry, removeEntry, submitOrQueue, syncEntry } from '@/lib/entryQueue';
type Catalog={restaurant_id:number;user_id:number;stock:{id:number;name:string;unit:string}[]};
type History={id:number;kind:string;at:string;by_you:boolean;undone:boolean;message:string;note:string};
type Bill={id:number;name:string;amount_kes:number;is_active?:boolean};
const field='block min-h-11 w-full rounded-lg border border-slate-300 bg-white p-2';
const button='min-h-11 rounded-lg border border-teal-800 px-4 py-2 font-semibold disabled:opacity-50';
export default function StockEntries({mode}:{mode?:string}){
 const {user}=useAuth(),owner=isOwnerAccount(user),role=user?.staff_role?.toLowerCase();
 const allowed=owner||['manager','stockkeeper','controller'].includes(role||'');
 const [catalog,setCatalog]=useState<Catalog|null>(null),[history,setHistory]=useState<History[]>([]),[bills,setBills]=useState<Bill[]>([]);
 const [kind,setKind]=useState(mode&&mode!=='queue'?mode:'count'),[item,setItem]=useState(''),[quantity,setQuantity]=useState(''),[note,setNote]=useState(''),[bill,setBill]=useState(''),[method,setMethod]=useState('cash');
 const [pending,setPending]=useState<PendingEntry[]>([]),[message,setMessage]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const locked=useRef(false),retry=useRef<string|null>(null);
 const captured=useRef('');
 const refresh=useCallback(async()=>{
  if(!user||!allowed)return;
  const [c,h]=await Promise.all([api.get('/api/v1/owner/operations/catalog'),api.get('/api/v1/owner/operations/entries')]);
  setCatalog(c.data);setHistory(h.data);localStorage.setItem(`leviii-catalog-${user.id}`,JSON.stringify(c.data));setPending(pendingEntries(user.id));
  if(owner||role==='manager')setBills((await api.get('/api/v1/owner/money/bills')).data.bills||[]);
 },[user,allowed,owner,role]);
 useEffect(()=>{if(!user||!allowed)return;refresh().catch(()=>{try{const saved=localStorage.getItem(`leviii-catalog-${user.id}`);if(saved)setCatalog(JSON.parse(saved));setPending(pendingEntries(user.id));}catch{}setError('Connection unavailable. Previously loaded stock lists can still capture entries for later review.');});},[refresh,user,allowed]);
 useEffect(()=>{if(!user)return;const reload=()=>setPending(pendingEntries(user.id));window.addEventListener('entry-queued',reload);return()=>window.removeEventListener('entry-queued',reload);},[user]);
 function failure(e:unknown){const x=e as {message?:string;response?:{data?:{detail?:string}}};return typeof x.response?.data?.detail==='string'?x.response.data.detail:x.message||'Could not save. Retry after checking your connection.';}
 async function run(task:()=>Promise<void>){if(locked.current)return;locked.current=true;setBusy(true);setError('');setMessage('');try{await task();}catch(e){setError(failure(e));}finally{locked.current=false;setBusy(false);}}
 async function save(e:FormEvent){e.preventDefault();if(!catalog||!user)return;await run(async()=>{
  if(!retry.current){retry.current=crypto.randomUUID();captured.current=new Date().toISOString();}const capturedAt=captured.current;
  const entry:PendingEntry={id:retry.current,userId:user.id,restaurantId:catalog.restaurant_id,url:'/api/v1/owner/operations/entries',label:kind,capturedAt,
   body:{restaurant_id:catalog.restaurant_id,entry_key:retry.current,kind,inventory_item_id:item?Number(item):null,quantity:kind==='bill'?0:Number(quantity),bill_id:bill?Number(bill):null,note,method,captured_at:capturedAt}};
  const result=await submitOrQueue(entry);setMessage(result.queued?'Saved on this device, awaiting sync. It is not yet in the restaurant records.':result.data.message);setPending(pendingEntries(user.id));retry.current=null;setQuantity('');setNote('');if(!result.queued)await refresh();
 });}
 if(!user||!allowed)return null;
 return <section className="space-y-4 rounded-xl border border-slate-300 p-4"><h2 className="text-xl font-semibold">{mode?({count:"Physical stock count",waste:"Waste / breakage",issue:"Issue to kitchen",bill:"Pay a bill",queue:"Waiting to sync"} as Record<string,string>)[mode]:"Stock counts, waste, kitchen issues & bills"}</h2><p>{mode?({count:"Count this item across all its locations. Enter your physical quantity before seeing the expected amount.",waste:"Write off an observed quantity with a reason. This is recorded waste, not an unexplained difference.",issue:"Declare what you send. A different person must confirm receipt before the handover is complete.",bill:"Record the saved bill amount as paid today.",queue:"Unsent records on this device. They are not included in restaurant totals until synced."} as Record<string,string>)[mode]:"Physical counts cover the whole item. Kitchen issues require independent confirmation."}</p>
 {error&&<p role="alert" className="rounded bg-red-100 p-3">{error}</p>}{message&&<p role="status" className="rounded bg-green-100 p-3">{message}</p>}
 {mode!=='queue'&&<form onSubmit={save} onChange={()=>{retry.current=null;}} className="space-y-3"><fieldset disabled={busy||!catalog} className="space-y-3">{!mode&&<label>Record<select aria-label="Stock entry type" className={field} value={kind} onChange={e=>setKind(e.target.value)}>{(['count','waste','issue',...(owner||role==='manager'?['bill']:[])]).map(k=><option key={k} value={k}>{({count:'Physical stock count',waste:'Waste / breakage',issue:'Issue to kitchen',bill:'Pay a bill'} as Record<string,string>)[k]}</option>)}</select></label>}
 {kind==='bill'?<><label>Bill<select className={field} required value={bill} onChange={e=>setBill(e.target.value)}><option value="">Choose bill</option>{bills.map(b=><option key={b.id} value={b.id}>{b.name} · KES {b.amount_kes}</option>)}</select></label><label>Paid by<select className={field} value={method} onChange={e=>setMethod(e.target.value)}>{['cash','mpesa','bank','card','other'].map(m=><option key={m}>{m}</option>)}</select></label><p>Records the bill’s saved amount as paid today. Adjust the bill first if the amount differs.</p></>:<><label>Stock item<select className={field} required value={item} onChange={e=>setItem(e.target.value)}><option value="">Choose stock item</option>{catalog?.stock.map(i=><option key={i.id} value={i.id}>{i.name} ({i.unit})</option>)}</select></label><label>{kind==='count'?'Quantity physically counted':'Quantity'}<input aria-label="Stock quantity" className={field} type="number" min={kind==='count'?'0':'0.000001'} step="any" required value={quantity} onChange={e=>setQuantity(e.target.value)}/></label></>}
 <label>Reason / shift reference<input className={field} required minLength={3} maxLength={500} value={note} onChange={e=>setNote(e.target.value)}/></label><button className={button} disabled={busy||!catalog}>Save stock or bill entry</button></fieldset></form>}
 {(!mode||mode==='issue')&&<Link className="inline-flex min-h-11 items-center underline" href={owner ? "/kitchen-stock" : role==='controller'?'/staff/controller/receiving':role==='stockkeeper'?'/staff/stockkeeper/receiving':'/staff/kitchen/stock'}>Kitchen handover confirmations →</Link>}
 {(!mode||mode==='queue')&&<> <h3 className="font-semibold">Waiting to sync ({pending.length})</h3>{pending.map(p=><div className="rounded border p-3" key={p.id}><p>{p.label} · branch {p.restaurantId} · captured {p.capturedAt}</p><button className={button} disabled={busy} onClick={()=>run(async()=>{const r=await syncEntry(p);setMessage(r.message||'Entry synced.');await refresh();})}>Sync this entry</button> <button className={button} disabled={busy} onClick={()=>{removeEntry(user.id,p.id);setPending(pendingEntries(user.id));}}>Discard unsent entry</button></div>)}
 <p className="text-sm">Sync uses the original retry key and branch. If stock has moved since an offline count, the server asks for a fresh count. Photos need a connection.</p>
</>} {mode!=='queue'&&<> <h3 className="font-semibold">Recent stock & bill entries</h3>{history.filter(h=>!mode||mode==='queue'||h.kind===mode).map(h=><div className="rounded border p-3" key={h.id}><p>{h.kind} · {h.at} · {h.note}</p><p>{h.message}{h.undone?' · Reversed':''}</p>{h.by_you&&!h.undone&&h.kind!=='market'&&Date.now()-Date.parse(`${h.at}Z`)<600000&&<button className={button} disabled={busy} onClick={()=>run(async()=>{const r=await api.post(`/api/v1/owner/operations/entries/${h.id}/undo`);setMessage(r.data.message);await refresh();})}>Undo my recent entry</button>}</div>)}</>}
 </section>;
}
