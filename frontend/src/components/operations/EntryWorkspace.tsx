"use client";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { homeFor, isOwnerAccount } from "@/lib/tenantHome";
import StockEntries from './StockEntries';
import AccountantReview from './AccountantReview';
import { submitOrQueue } from '@/lib/entryQueue';

type Stock = {id:number;name:string;unit:string;on_hand:number;par:number|null;buying_unit:string;factor:number};
type PO = {id:number;item_name:string;supplier_name:string;quantity_ordered:number;unit:string;inventory_item_id:number;status:string;invoice_ref?:string|null};
type Category = {key:string;name:string};
const field="block min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900";
const button="min-h-11 rounded-lg bg-teal-800 px-4 py-2 font-semibold text-white disabled:opacity-50";
function message(e:unknown) { const x=e as {response?:{data?:{detail?:unknown}}}; return typeof x.response?.data?.detail==='string'?x.response.data.detail:'Could not save. Check the fields and connection, then retry.'; }
const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Africa/Nairobi',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
export function cents(value:string):number { if(!/^\d+(\.\d{1,2})?$/.test(value)) throw new Error('Enter shillings with at most two decimal places'); const [whole,part='']=value.split('.'); return Number(whole)*100+Number(part.padEnd(2,'0')); }
async function receiptPhoto(file:File):Promise<Blob> {
 if(file.size<=750000)return file;
 const image=await createImageBitmap(file);
 try {
  const canvas=document.createElement('canvas');const scale=Math.min(1,1400/Math.max(image.width,image.height));
  canvas.width=Math.round(image.width*scale);canvas.height=Math.round(image.height*scale);
  const context=canvas.getContext('2d');if(!context)throw new Error('Could not resize this photo. Choose a smaller image.');
  context.drawImage(image,0,0,canvas.width,canvas.height);
  for(const quality of [.8,.6,.4]){const blob=await new Promise<Blob|null>(resolve=>canvas.toBlob(resolve,'image/jpeg',quality));if(blob&&blob.size<=750000)return blob;}
  throw new Error('Choose a smaller photo so it can be saved clearly.');
 }finally{image.close();}
}
export default function EntryWorkspace() {
 const {user,isLoading}=useAuth();
 const owner=isOwnerAccount(user); const role=user?.staff_role?.toLowerCase();
 const money=owner||role==='manager'||role==='controller'; const receiving=owner||role==='manager'||role==='stockkeeper';
 const [categories,setCategories]=useState<Category[]>([]),[stock,setStock]=useState<Stock[]>([]),[orders,setOrders]=useState<PO[]>([]);
 const [restaurantId,setRestaurantId]=useState<number|null>(null);
 const [error,setError]=useState(''),[success,setSuccess]=useState(''),[busy,setBusy]=useState(false);
 const locked=useRef(false),entryKey=useRef<string|null>(null);
 const [tab,setTab]=useState('expense'),[category,setCategory]=useState(''),[amount,setAmount]=useState(''),[method,setMethod]=useState('cash');
 const [photo,setPhoto]=useState<File|null>(null),[poId,setPoId]=useState(''),[qty,setQty]=useState(''),[units,setUnits]=useState('counting');
 const [day,setDay]=useState(today),[start,setStart]=useState('08:00'),[end,setEnd]=useState('16:00'),[counted,setCounted]=useState('');
 const [month,setMonth]=useState(()=>today().slice(0,7));
 const [itemId,setItemId]=useState(''),[buying,setBuying]=useState(''),[factor,setFactor]=useState('1');
 const allowed=money||receiving;
 const load=useCallback(async()=>{
  const catalog=await api.get('/api/v1/owner/operations/catalog');setStock(catalog.data.stock);setRestaurantId(catalog.data.restaurant_id||null);
  if(money){const c=await api.get('/api/v1/owner/money/categories');setCategories(c.data.categories);}
  if(receiving){const p=await api.get('/api/v1/purchase-orders/');setOrders(p.data);}
 },[money,receiving]);
 useEffect(()=>{if(user&&allowed)load().catch(e=>setError(message(e)));},[user,allowed,load]);
 async function upload() {
  if(!photo)return undefined;
  const resized=await receiptPhoto(photo);
  const data=new FormData();data.append('file',resized,'receipt.jpg');
  const r=await api.post('/api/v1/owner/operations/receipts',data,{headers:{'Content-Type':'multipart/form-data'}});return r.data.receipt_ref as string;
 }
 async function save(e:FormEvent) {
  e.preventDefault();if(locked.current)return;locked.current=true;setBusy(true);setError('');setSuccess('');
  entryKey.current??=crypto.randomUUID();
  try {
   if(tab==='expense') {
    const ref=await upload();
    const body={category,amount_kes:(cents(amount)/100).toFixed(2),method,receipt_ref:ref,entry_key:entryKey.current,paid_on:today(),...(restaurantId?{expected_restaurant_id:restaurantId}:{})};
    if(!photo&&restaurantId&&user){const result=await submitOrQueue({id:entryKey.current,userId:user.id,restaurantId,url:'/api/v1/owner/money/expenses',body,label:'Expense',capturedAt:new Date().toISOString()});if(result.queued){setSuccess('Expense saved on this device, awaiting sync in the queue below. It is not in Profit & Loss yet.');entryKey.current=null;setAmount('');window.dispatchEvent(new Event('entry-queued'));return;}}
    else await api.post('/api/v1/owner/money/expenses',body);
    setSuccess('Expense saved. It is now included in Profit & Loss.');setAmount('');
   } else if(tab==='cash') {
    const lo=new Date(`${day}T${start}:00+03:00`),hi=new Date(`${day}T${end}:00+03:00`);
    if(hi<=lo)hi.setUTCDate(hi.getUTCDate()+1);
    const body={counted_amount_cents:cents(counted),window_start:lo.toISOString(),window_end:hi.toISOString(),entry_key:entryKey.current,...(restaurantId?{expected_restaurant_id:restaurantId}:{})};
    const result=restaurantId&&user?await submitOrQueue({id:entryKey.current,userId:user.id,restaurantId,url:'/api/v1/cash-reconciliation/counts',body,label:'Cash count',capturedAt:new Date().toISOString()}):{queued:false,data:(await api.post('/api/v1/cash-reconciliation/counts',body)).data};
    if(result.queued){setSuccess('Cash count saved on this device; sync it below to include it in the owner report.');entryKey.current=null;setCounted('');window.dispatchEvent(new Event('entry-queued'));return;}
    const gap=(result.data.counted_amount_cents-result.data.expected_amount_cents)/100;
    setSuccess(`Count saved. Difference from recorded cash sales: KES ${gap.toLocaleString('en-KE')}. The owner can review it.`);setCounted('');
   } else if(tab==='delivery') {
    const ref=await upload();const r=await api.post(`/api/v1/owner/operations/deliveries/${poId}/receive`,{quantity:Number(qty),units,invoice_ref:ref});
    setSuccess(`Delivery saved: ${r.data.received} counting units. ${r.data.status==='PARTIAL'?'Short delivery recorded for review.':'Stock updated.'}`);setQty('');await load();
   } else if(tab==='units') {
    await api.put(`/api/v1/owner/operations/units/${itemId}`,{buying_unit:buying,factor:Number(factor)});setSuccess('Buying-unit conversion saved. Quantities and costs stay in counting units.');await load();
   }
   entryKey.current=null;setPhoto(null);
  }catch(e){setError(e instanceof Error&&!('response' in e)?e.message:message(e));}finally{setBusy(false);locked.current=false;}
 }
 async function download(format:string){if(locked.current)return;locked.current=true;setBusy(true);setError('');try{const r=await api.get(`/api/v1/owner/money/pnl/export?month=${month}&format=${format}`,{responseType:'blob'});const url=URL.createObjectURL(r.data);const a=document.createElement('a');a.href=url;a.download=`profit-loss-${month}.${format}`;a.click();URL.revokeObjectURL(url);}catch(e){setError(message(e));}finally{locked.current=false;setBusy(false);}}
 if(isLoading)return <p role="status">Checking access…</p>;
 if(!user)return <Link href="/login">Sign in to record entries</Link>;
 if(!allowed)return <p role="alert">Your role cannot record these entries.</p>;
 const current=money?tab:tab==='expense'?'delivery':tab;
 const selected=orders.find(p=>p.id===Number(poId)); const inv=stock.find(i=>i.id===selected?.inventory_item_id);
 return <div className="mx-auto max-w-2xl space-y-5 p-4 text-slate-900">
  <Link href={homeFor(user)} className="inline-flex min-h-11 items-center text-teal-800">← Back to your workspace</Link>
  <h1 className="text-3xl font-semibold">Team entries</h1><p>Record what actually happened. Amounts are in KES; times are Nairobi time.</p>
  {user.tenant_name==='Demo Restaurant'&&<p className="rounded-lg bg-amber-100 p-3">Illustrative demo — entries change the demo only.</p>}
  <nav aria-label="Entry types" className="flex flex-wrap gap-2">{[...(money?['expense',...(role!=='controller'?['cash']:[]),'export']:[]),...(receiving?['delivery']:[]),...(owner||role==='manager'?['units']:[])].map(t=><button type="button" key={t} disabled={busy} aria-pressed={current===t} className={button} onClick={()=>{setTab(t);entryKey.current=null;setError('');setSuccess('');setPhoto(null);}}>{({expense:'Expense',cash:'Close shift',export:'Accountant export',delivery:'Receive delivery',units:'Buying units'} as Record<string,string>)[t]}</button>)}</nav>
  {error&&<p role="alert" className="rounded-lg bg-red-100 p-3">{error}</p>}{success&&<p role="status" className="rounded-lg bg-green-100 p-3">{success}</p>}
  {current==='export'?<section className="space-y-4"><label>Month<input aria-label="Export month" className={field} type="month" max={today().slice(0,7)} value={month} onChange={e=>setMonth(e.target.value)}/></label><div className="flex gap-3">{['xlsx','pdf'].map(f=><button type="button" className={button} disabled={busy} key={f} onClick={()=>download(f)}>Download {f.toUpperCase()}</button>)}</div><p>Exports include the recorded costs and their completeness labels.</p></section>:
  <form onSubmit={save} className="space-y-4" onChange={()=>{if(!busy)entryKey.current=null;}}>
   <fieldset disabled={busy} className="space-y-4">
   {current==='expense'&&<><label className="block">Cost category<select aria-label="Cost category" className={field} required value={category} onChange={e=>setCategory(e.target.value)}><option value="">Choose category</option>{categories.map(c=><option value={c.key} key={c.key}>{c.name}</option>)}</select></label><label className="block">Amount (KES)<input aria-label="Amount (KES)" className={field} inputMode="decimal" required value={amount} onChange={e=>setAmount(e.target.value)}/></label><label className="block">Paid by<select className={field} value={method} onChange={e=>setMethod(e.target.value)}>{['cash','mpesa','bank','card','other'].map(m=><option key={m}>{m}</option>)}</select></label></>}
   {current==='cash'&&<><p>Count the cash before saving. Expected cash stays hidden until your count is recorded. No till prices are changed.</p><label className="block">Shift start date<input className={field} type="date" required max={today()} value={day} onChange={e=>setDay(e.target.value)}/></label><div className="grid grid-cols-2 gap-3"><label>Start time<input className={field} type="time" required value={start} onChange={e=>setStart(e.target.value)}/></label><label>End time<input className={field} type="time" required value={end} onChange={e=>setEnd(e.target.value)}/></label></div><p className="text-sm">If end is before start, the shift ends the following day.</p><label className="block">Cash physically counted (KES)<input aria-label="Cash physically counted (KES)" className={field} inputMode="decimal" required value={counted} onChange={e=>setCounted(e.target.value)}/></label></>}
   {current==='delivery'&&<><label className="block">Expected delivery<select aria-label="Expected delivery" className={field} value={poId} required onChange={e=>{setPoId(e.target.value);setUnits('counting');setQty('');setTab('delivery');}}><option value="">Choose delivery</option>{orders.filter(p=>p.status==='SENT').map(p=><option value={p.id} key={p.id}>{p.supplier_name} · {p.item_name} · {p.quantity_ordered} {p.unit}</option>)}</select></label>{!orders.some(p=>p.status==='SENT')&&<p>No sent purchase orders are awaiting delivery.</p>}<label className="block">Quantity actually received<input aria-label="Quantity actually received" className={field} type="number" min="0" step="any" required value={qty} onChange={e=>{setQty(e.target.value);setTab('delivery');}}/></label><label className="block">Receive in<select className={field} value={units} onChange={e=>setUnits(e.target.value)}><option value="counting">{selected?.unit||'Counting units'}</option>{inv?.buying_unit&&<option value="buying">{inv.buying_unit} ({inv.factor} {inv.unit} each)</option>}</select></label>{selected&&qty!==''&&<p>Ordered {selected.quantity_ordered} {selected.unit}; receiving {Number(qty)*(units==='buying'?(inv?.factor||1):1)} {selected.unit}.</p>}</>}
   {current==='units'&&<><p>Set the unit you buy and how many counting units it contains. This does not change existing stock or order quantities.</p><label>Stock item<select className={field} value={itemId} required onChange={e=>{setItemId(e.target.value);const i=stock.find(i=>i.id===Number(e.target.value));setBuying(i?.buying_unit||'');setFactor(String(i?.factor||1));}}><option value="">Choose stock item</option>{stock.map(i=><option key={i.id} value={i.id}>{i.name} · counted in {i.unit}</option>)}</select></label><label>Buying unit<input className={field} required maxLength={40} placeholder="crate, sack, carton…" value={buying} onChange={e=>setBuying(e.target.value)}/></label><label>Counting units in one buying unit<input className={field} required type="number" min="0.000001" step="any" value={factor} onChange={e=>setFactor(e.target.value)}/></label></>}
   {(current==='expense'||current==='delivery')&&<label className="block">Receipt / invoice photo (optional; large photos are resized)<input key={photo?'attached':'empty'} className={field} type="file" accept="image/*" capture="environment" onChange={e=>{setPhoto(e.target.files?.[0]||null);if(current==='delivery')setTab('delivery');}}/></label>}
   <button className={button} disabled={busy} type="submit">{busy?'Saving…':current==='cash'?'Save blind count':current==='delivery'?'Save delivery':current==='units'?'Save conversion':'Save expense'}</button>
   </fieldset>
  </form>}
  {receiving&&<section className="space-y-2"><h2 className="text-xl font-semibold">Recent deliveries</h2>{orders.filter(p=>p.status==='DELIVERED'||p.status==='PARTIAL').slice(0,8).map(p=><div key={p.id} className="rounded-lg border border-slate-200 p-3"><p>{p.item_name} · {p.supplier_name} · {p.status}</p>{p.invoice_ref&&<button className="min-h-11 underline" type="button" onClick={async()=>{try{const r=await api.get(`/api/v1/owner/operations/receipts/${p.invoice_ref?.split('/').pop()}`,{responseType:'blob'});const u=URL.createObjectURL(r.data);const a=document.createElement('a');a.href=u;a.download='invoice.jpg';a.click();URL.revokeObjectURL(u);}catch(e){setError(message(e));}}}>Download invoice photo</button>}</div>)}</section>}
  <StockEntries/>
  {money&&<AccountantReview/>}
 </div>;
}
