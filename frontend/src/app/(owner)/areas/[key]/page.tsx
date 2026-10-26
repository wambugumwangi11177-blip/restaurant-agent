"use client";
import {useDailyReview} from "@/lib/owner/useDailyReview";
import { Suspense, use, useEffect, useState } from "react";
import Link from "next/link";
import api from "@/lib/api";
import { AreaFocus } from "@/components/owner/areas/ui";
import AreaBody from "@/components/owner/AreaBody";
import { AREA_KEYS, type Area } from "@/lib/owner/types";
import { AREA_TITLES, BLOCK_TITLES } from "@/lib/owner/blocks";
import { FEATURE_GROUPS, blockAnchor } from "@/lib/owner/features";
import { useToolSelection } from "@/lib/owner/useToolSelection";
import { OsLoading, OsError } from "@/components/os/States";

function AreaWorkspace({params}:{params:Promise<{key:string}>}) {
 const {key}=use(params);
 const tool=useToolSelection();
 const reviewDay=useDailyReview();
 const [area,setArea]=useState<Area|null>(null),[error,setError]=useState(false),[retry,setRetry]=useState(0);
 const valid=AREA_KEYS.includes(key as typeof AREA_KEYS[number]);
 useEffect(()=>{
  if(!valid)return;
  let active=true;
  api.get<Area>(`/api/v1/owner/area/${key}`).then(r=>{if(active){setArea(r.data);setError(false);}}).catch(()=>{if(active)setError(true);});
  return()=>{active=false;};
 },[key,retry,valid,reviewDay]);
 if(!valid)return <p>This restaurant area does not exist. <Link href="/explore">Explore your tools</Link></p>;
 const group=FEATURE_GROUPS.find(g=>g.area===key)!;
 const sections=[...Object.values(BLOCK_TITLES[group.area]),...(key==="money"?["Price impact"]:[]),...(key==="sales_dishes"?["Best and weakest hours","Unusual sales days"]:[]),...(key=="permits"?["Source readiness"]:[]),...(key==="staff"?["Sales per staff hour","Overtime"]:[])];
 const selected=sections.find(title=>blockAnchor(title)===tool);

 return <div className="space-y-6">
  <Link href={`/explore?area=${key}`} className="inline-flex min-h-11 items-center text-sm font-semibold text-[var(--v-primary)]">← {group.title} tools</Link>
  <header><p className="leviii-eyebrow">{AREA_TITLES[group.area]}</p><h1 className="font-display text-4xl font-semibold">{selected ?? (tool?"Tool not found":"Choose a tool")}</h1></header>
  {!tool||tool==='ingredients-and-wages'?<section aria-label="Choose one tool" className="grid gap-3 sm:grid-cols-2">{group.items.map(item=><Link key={item.title} href={item.href} className="rounded-xl border border-[var(--v-border)] bg-white p-4 font-semibold">{item.title} →</Link>)}</section>:!selected?<p role="alert">This tool link is not recognised. <Link href={`/explore?area=${key}`} className="underline">Choose a tool</Link>.</p>:error?<OsError message="Could not load this tool's data." onRetry={()=>setRetry(n=>n+1)}/>:area?.key===key?<div data-testid="selected-area-tool" data-tool={tool} className="leviii-focused-tool"><AreaFocus.Provider value={tool}><AreaBody key={`${key}:${tool}`} area={area}/></AreaFocus.Provider></div>:<OsLoading/>}
 </div>;
}
export default function AreaPage(props:{params:Promise<{key:string}>}) {
 return <Suspense fallback={<OsLoading/>}><AreaWorkspace {...props}/></Suspense>;
}
