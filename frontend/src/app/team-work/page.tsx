"use client";
import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import api from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { homeFor, isOwnerAccount } from '@/lib/tenantHome';
import { getErrorMessage } from '@/lib/errors';

type Item = {id:number;kind:string;title:string;status:string;revision:number;created_by:number;assigned_to:number|null;due_on:string|null;overdue:boolean;details:{request:{reason:string;expense_id?:number;quantity?:number};item_name?:string;unit?:string}};
type Event = {id:number;title:string;action:string;note:string;actor_id:number;created_at:string};
type Person = {id:number;name:string};
const field='block min-h-11 w-full rounded-lg border border-slate-600 bg-slate-900 p-3 text-white';
const button='min-h-11 rounded-lg border border-amber-400 px-4 py-2 text-amber-200 disabled:opacity-40';
export default function TeamWork(){
 const {user,isLoading}=useAuth(); const owner=isOwnerAccount(user);const manager=owner||user?.staff_role==='manager';
 const [items,setItems]=useState<Item[]>([]),[events,setEvents]=useState<Event[]>([]),[people,setPeople]=useState<Person[]>([]);
 const [rid,setRid]=useState<number|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 const [kind,setKind]=useState('task'),[title,setTitle]=useState(''),[reason,setReason]=useState(''),[assigned,setAssigned]=useState(''),[due,setDue]=useState(''),[target,setTarget]=useState(''),[quantity,setQuantity]=useState(''),[review,setReview]=useState('');
 const [more,setMore]=useState<number|null>(null),[moreEvents,setMoreEvents]=useState<number|null>(null);
 const [options,setOptions]=useState<{stock:{id:number;name:string;unit:string}[];expenses:{id:number;name:string;amount_cents:number}[]}>({stock:[],expenses:[]});
 const key=useRef<string|null>(null),lock=useRef(false);
 const load=useCallback(async()=>{
  const [work,feed]=await Promise.all([api.get('/api/v1/team-work'),api.get('/api/v1/team-work/activity')]);
  setItems(work.data.items);setRid(work.data.restaurant_id);setMore(work.data.next_before);setEvents(feed.data.items);setMoreEvents(feed.data.next_before);
  setOptions((await api.get('/api/v1/team-work/options')).data);
  if(manager)setPeople((await api.get('/api/v1/team-work/people')).data.items);
 },[manager]);
 useEffect(()=>{if(user)void load().catch(e=>setError(getErrorMessage(e,'Could not load team work.')));},[user,load]);
 async function run(work:()=>Promise<void>){if(lock.current)return;lock.current=true;setBusy(true);setError('');setMessage('');try{await work();}catch(e){setError(getErrorMessage(e,'Could not save. Reload and retry.'));}finally{lock.current=false;setBusy(false);}}
 async function save(e:FormEvent){e.preventDefault();await run(async()=>{
  key.current??=crypto.randomUUID();
  await api.post('/api/v1/team-work',{request_key:key.current,restaurant_id:rid,kind,title,reason,
   ...(kind==='task'?{assigned_to:Number(assigned),due_on:due||null}:kind==='expense_void'?{expense_id:Number(target)}:{inventory_item_id:Number(target),quantity:Number(quantity)})});
  key.current=null;setTitle('');setReason('');setTarget('');setQuantity('');setMessage('Saved. Approval requests do not change records until a different owner approves.');await load();
 });}
 async function change(item:Item,action:string){await run(async()=>{await api.post(`/api/v1/team-work/${item.id}/transition`,{revision:item.revision,action,note:review});setMessage('Updated with an audit record.');await load();});}
 if(isLoading)return <p role="status">Checking access…</p>;
 if(!user)return <Link href="/login">Sign in</Link>;
 const choices=[...(manager?['task']:[]),...(manager||user.staff_role==='controller'?['expense_void']:[]),...(manager||['stockkeeper','kitchen'].includes(user.staff_role||'')?['spoilage']:[])];
 const labels:Record<string,string>={task:'Assign a task',expense_void:'Propose expense reversal',spoilage:'Request spoilage write-off'};
 return <main className="min-h-screen bg-slate-950 p-4 text-slate-100 sm:p-8"><div className="mx-auto max-w-4xl space-y-6">
  <Link className="inline-flex min-h-11 items-center underline" href={homeFor(user)}>← Back to your workspace</Link>
  <h1 className="text-3xl font-semibold">Team work & approvals</h1><p>Only work you created, work assigned to you, and owner-visible requests appear here. Times are Nairobi time.</p>
  {error&&<p role="alert" className="text-red-300">{error}</p>}{message&&<p role="status">{message}</p>}
  <button className={button} disabled={busy} onClick={()=>run(load)}>Refresh</button>
  {choices.length>0&&<form className="space-y-3 rounded-xl border border-slate-700 p-4" onSubmit={save} onChange={()=>{if(!busy)key.current=null;}}><h2 className="text-xl">New work</h2><fieldset disabled={busy||rid===null} className="space-y-3">
   <label>Type<select className={field} value={choices.includes(kind)?kind:''} required onChange={e=>setKind(e.target.value)}><option value="" disabled>Choose type</option>{choices.map(c=><option key={c} value={c}>{labels[c]}</option>)}</select></label>
   <label>Title<input className={field} required minLength={3} maxLength={160} value={title} onChange={e=>setTitle(e.target.value)}/></label>
   <label>Reason and evidence<textarea className={field} required minLength={3} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/></label>
   {kind==='task'?<><label>Assign to<select className={field} required value={assigned} onChange={e=>setAssigned(e.target.value)}><option value="">Choose teammate</option>{people.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><label>Due date (optional)<input className={field} type="date" value={due} onChange={e=>setDue(e.target.value)}/></label></>:<><label>{kind==='expense_void'?'Expense to review (latest 100)':'Stock item'}<select className={field} required value={target} onChange={e=>setTarget(e.target.value)}><option value="">Choose a record</option>{(kind==='expense_void'?options.expenses.map(e=>({id:e.id,label:`${e.name} · KES ${(e.amount_cents/100).toLocaleString('en-KE')}`})):options.stock.map(i=>({id:i.id,label:`${i.name} · ${i.unit}`}))).map(o=><option key={o.id} value={o.id}>{o.label}</option>)}</select></label>{kind==='spoilage'&&<label>Quantity in the item’s counting unit<input className={field} type="number" min="0.000001" step="any" required value={quantity} onChange={e=>setQuantity(e.target.value)}/></label>}<p>A different owner reviews this request. Changed records require a fresh request.</p></>}
   <button className={button} type="submit">Save request</button></fieldset></form>}
  <section className="space-y-3"><h2 className="text-xl font-semibold">Requests and tasks</h2><label>Review or completion note<textarea className={field} minLength={3} maxLength={500} value={review} onChange={e=>setReview(e.target.value)}/></label>
   {items.length===0&&<p>No work recorded yet.</p>}{items.map(item=><article key={item.id} className="space-y-2 rounded-xl border border-slate-700 p-4"><h3 className="font-semibold">{item.title}</h3><p>{item.status.replaceAll('_',' ')}{item.overdue?' · Overdue':''}{item.due_on?` · Due ${item.due_on}`:''}</p><p>{item.details.request.reason}</p>{item.details.request.expense_id&&<p>Expense #{item.details.request.expense_id}</p>}{item.details.item_name&&<p>{item.details.item_name}: {item.details.request.quantity} {item.details.unit}</p>}
    {['pending','in_progress'].includes(item.status)&&<div className="flex flex-wrap gap-2">{(item.kind==='task'?(owner||item.assigned_to===user.id?item.status==='pending'?['start','complete']:['complete']:[]):owner&&item.created_by!==user.id?['approve','reject']:[]).map(action=><button key={action} className={button} disabled={busy||review.trim().length<3} onClick={()=>change(item,action)}>{action[0].toUpperCase()+action.slice(1)}</button>)}</div>}
   </article>)}{more&&<button className={button} disabled={busy} onClick={()=>run(async()=>{const r=await api.get(`/api/v1/team-work?before=${more}`);setItems(v=>[...v,...r.data.items]);setMore(r.data.next_before);})}>Older work</button>}</section>
  <section className="space-y-3"><h2 className="text-xl font-semibold">Work activity</h2><p>Requests, approvals and task updates. Other operational records remain in their existing screens.</p>{events.map(e=><article className="border-b border-slate-700 py-2" key={e.id}><p>{e.title} · {e.action.replaceAll('_',' ')}</p><p>{e.note}</p><small>Person #{e.actor_id} · {new Date(e.created_at+'Z').toLocaleString('en-KE',{timeZone:'Africa/Nairobi'})}</small></article>)}{moreEvents&&<button className={button} disabled={busy} onClick={()=>run(async()=>{const r=await api.get(`/api/v1/team-work/activity?before=${moreEvents}`);setEvents(v=>[...v,...r.data.items]);setMoreEvents(r.data.next_before);})}>Older activity</button>}</section>
 </div></main>;
}
