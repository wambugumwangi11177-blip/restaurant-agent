"use client";
import {useSyncExternalStore} from 'react';
const subscribe=(notify:()=>void)=>{window.addEventListener('popstate',notify);window.addEventListener('leviii-query',notify);return()=>{window.removeEventListener('popstate',notify);window.removeEventListener('leviii-query',notify);};};
export function useListQuery(name:string,fallback='') {
 const search=useSyncExternalStore(subscribe,()=>window.location.search,()=> '');
 const value=new URLSearchParams(search).get(name)??fallback;
 const set=(next:string,replace=false)=>{const url=new URL(window.location.href);if(next)url.searchParams.set(name,next);else url.searchParams.delete(name);if(name!=='page')url.searchParams.delete('page');window.history[replace?'replaceState':'pushState']({},'',url);window.dispatchEvent(new Event('leviii-query'));};
 return [value,set] as const;
}
