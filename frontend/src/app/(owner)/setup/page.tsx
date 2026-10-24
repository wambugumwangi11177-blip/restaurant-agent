"use client";
import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
type Step={key:string;title:string;count:number;detail:string;href:string;review:null|{by:number;at:string;note:string}};
type Setup={restaurant_id:number;steps:Step[];notice:string};
export default function SetupPage(){
 const [data,setData]=useState<Setup|null>(null),[index,setIndex]=useState(0),[note,setNote]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);const locked=useRef(false);
 const load=useCallback(async()=>{setData((await api.get('/api/v1/owner/setup')).data);},[]);
 useEffect(()=>{void load().catch(e=>setError(getErrorMessage(e,'Could not load setup.')));},[load]);
 const step=data?.steps[index];
 async function review(){if(!data||!step||locked.current)return;locked.current=true;setBusy(true);setError('');try{await api.post(`/api/v1/owner/setup/${step.key}/review`,{restaurant_id:data.restaurant_id,note});await load();setNote('');setIndex(i=>Math.min(i+1,data.steps.length-1));}catch(e){setError(getErrorMessage(e,'Could not record your review.'));}finally{locked.current=false;setBusy(false);}}
 return <section className="space-y-5"><h1 className="text-3xl font-semibold">Set up this branch</h1><p>Work through one area at a time with Eleven’s team. Your review is saved, so you can return later.</p>{error&&<p role="alert">{error}</p>}
 {data&&step?<><p>{data.steps.filter(s=>s.review).length} of {data.steps.length} areas reviewed</p><nav aria-label="Setup steps" className="flex flex-wrap gap-2">{data.steps.map((s,i)=><button className="min-h-11 rounded border border-[var(--v-border)] p-2" key={s.key} aria-current={i===index?'step':undefined} disabled={busy} onClick={()=>{setIndex(i);setNote('');}}>{i+1}. {s.title}{s.review?' ✓':''}</button>)}</nav>
 <article className="space-y-4 rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5"><h2 className="text-xl font-semibold">{step.title}</h2><p>{step.count} records currently in this branch.</p><p>{step.detail}</p><Link className="inline-flex min-h-11 items-center underline" href={step.href}>Open the workspace for this step →</Link>
 {step.review?<div role="status"><p>Reviewed on {new Date(step.review.at+'Z').toLocaleDateString('en-KE',{timeZone:'Africa/Nairobi'})}</p><p>{step.review.note}</p><p>Check again if the source records or operating process changes.</p></div>:<><label className="block">What did you verify, and with whom?<textarea minLength={10} maxLength={500} value={note} onChange={e=>setNote(e.target.value)} className="mt-2 block min-h-24 w-full rounded border border-[var(--v-border)] bg-[var(--v-bg)] p-3"/></label><button className="min-h-11 rounded bg-[var(--v-primary)] px-4 text-[var(--v-primary-foreground)] disabled:opacity-50" disabled={busy||note.trim().length<10} onClick={review}>Save review and continue</button></>}
 </article><div className="flex justify-between"><button className="min-h-11 underline" disabled={busy||index===0} onClick={()=>{setIndex(index-1);setNote('');}}>Previous</button><button className="min-h-11 underline" disabled={busy||index===data.steps.length-1} onClick={()=>{setIndex(index+1);setNote('');}}>Next</button></div><p className="text-sm text-[var(--v-muted-foreground)]">{data.notice}</p></>:!error&&<p role="status">Loading setup…</p>}
 </section>;
}
