import api from '@/lib/api';
export type PendingEntry={id:string;userId:number;restaurantId:number;url:string;body:Record<string,unknown>;label:string;capturedAt:string};
const key='leviii-team-entries-v1';
export function pendingEntries(userId:number):PendingEntry[]{
 const raw=localStorage.getItem(key);if(!raw)return [];
 const rows=JSON.parse(raw) as PendingEntry[];
 return rows.filter(r=>r.userId===userId);
}
export function queueEntry(entry:PendingEntry){
 const rows=JSON.parse(localStorage.getItem(key)||'[]') as PendingEntry[];
 localStorage.setItem(key,JSON.stringify([...rows.filter(r=>r.id!==entry.id||r.userId!==entry.userId),entry]));
}
export function removeEntry(userId:number,id:string){
 const rows=JSON.parse(localStorage.getItem(key)||'[]') as PendingEntry[];
 localStorage.setItem(key,JSON.stringify(rows.filter(r=>r.userId!==userId||r.id!==id)));
}
export async function submitOrQueue(entry:PendingEntry){
 try{return {queued:false,data:(await api.post(entry.url,entry.body)).data};}
 catch(e){const response=(e as {response?:unknown}).response;if(response)throw e;queueEntry(entry);return {queued:true,data:null};}
}
export async function syncEntry(entry:PendingEntry){
 const scope=(await api.get('/api/v1/owner/operations/catalog')).data;
 if(scope.user_id!==entry.userId||scope.restaurant_id!==entry.restaurantId)throw new Error('Switch back to the account and branch where this entry was captured.');
 const result=await api.post(entry.url,entry.body);removeEntry(entry.userId,entry.id);return result.data;
}
