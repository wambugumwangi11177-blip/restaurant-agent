import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import ForecastPlanner from '@/components/owner/ForecastPlanner';
import GrowthTools from '@/components/owner/GrowthTools';
import StockEntries from '@/components/operations/StockEntries';
import { pendingEntries, submitOrQueue, syncEntry, PendingEntry } from '@/lib/entryQueue';
const api=vi.hoisted(()=>({get:vi.fn(),post:vi.fn(),put:vi.fn(),delete:vi.fn()}));
const account=vi.hoisted(()=>({id:1,role:'admin',staff_role:'owner'}));
vi.mock('@/lib/api',()=>({default:api}));
vi.mock('@/context/AuthContext',()=>({useAuth:()=>({user:account,isLoading:false})}));
beforeEach(()=>{vi.clearAllMocks();localStorage.clear();});
afterEach(cleanup);
const pending:PendingEntry={id:'retry-key-123',userId:1,restaurantId:202,url:'/api/v1/owner/operations/entries',label:'Waste',capturedAt:'2026-10-23T10:00:00Z',body:{entry_key:'retry-key-123',restaurant_id:202,kind:'waste',quantity:2}};

it('keeps a failed network submission on device without claiming it reached the ledger',async()=>{
 api.post.mockRejectedValue(new Error('network down'));
 const saved=await submitOrQueue(pending);expect(saved.queued).toBe(true);
 expect(pendingEntries(1)).toEqual([pending]);expect(pendingEntries(2)).toEqual([]);
 api.get.mockResolvedValue({data:{restaurant_id:303,user_id:1}});
 await expect(syncEntry(pending)).rejects.toThrow('Switch back');
 expect(api.post).toHaveBeenCalledTimes(1);
 api.get.mockResolvedValue({data:{restaurant_id:202,user_id:1}});api.post.mockResolvedValue({data:{message:'Recorded'}});
 await syncEntry(pending);
 expect(api.post).toHaveBeenLastCalledWith(pending.url,pending.body);expect(pendingEntries(1)).toEqual([]);
});

it('does not queue rejected server inputs',async()=>{
 api.post.mockRejectedValue({response:{status:409,data:{detail:'Stock changed'}}});
 await expect(submitOrQueue(pending)).rejects.toHaveProperty('response.status',409);
 expect(pendingEntries(1)).toEqual([]);
});

it('connects accepted forecast portions to raw prep and retry-safe supplier drafts',async()=>{
 api.get.mockImplementation(async(url:string)=>({data:url.includes('forecast')?{state:'live',note:'Recorded matching weekdays',observed_days:['2026-10-16'],dishes:[{menu_item_id:5,dish:'Stew',portions:8,low:6,high:9,has_recipe:true}]}:{suppliers:[{id:3,name:'Farm'}]}}));
 api.post.mockImplementation(async(url:string)=>({data:url.endsWith('/prep')?{items:[{inventory_item_id:7,item:'Beef',unit:'kg',need:2,on_hand:1,buffer:1,buy:2,supplier:'Farm',supplier_id:3,cost_per_unit_cents:50000}]}:{message:'1 draft lines saved'}}));
 render(<ForecastPlanner/>);fireEvent.click(screen.getByRole('button',{name:'Suggest portions from sales'}));
 await screen.findByLabelText('Stew forecast portions');fireEvent.change(screen.getByLabelText('Stew forecast portions'),{target:{value:'10'}});
 fireEvent.click(screen.getByRole('button',{name:'Accept portions & calculate market list'}));
 await screen.findByLabelText('Beef supplier');
 expect(api.post).toHaveBeenCalledWith('/api/v1/owner/planning/prep',{dishes:[{menu_item_id:5,portions:10}]});
 fireEvent.click(screen.getByRole('button',{name:'Save supplier purchase drafts'}));
 expect(await screen.findByRole('status')).toHaveProperty('textContent','1 draft lines saved');
 expect(api.post).toHaveBeenLastCalledWith('/api/v1/owner/planning/market-drafts',expect.objectContaining({dishes:[{menu_item_id:5,portions:10}],entry_key:expect.any(String),suppliers:{7:3}}));
});

it('loads a priced Star–Puzzle candidate into the existing checker',async()=>{
 api.get.mockImplementation(async(url:string)=>({data:url.endsWith('prices')?[]:{state:'live',note:'Recorded paid sales',items:[],gaps:[],tail_ingredients:0,results:[],combos:[{ids:[1,2],dishes:['Fish','Stew'],minimum_kes:1050,regular_kes:1200,floor_pct:40}]}}));
 const onCombo=vi.fn();render(<GrowthTools onCombo={onCombo}/>);
 fireEvent.click(await screen.findByRole('button',{name:'Try in combo checker'}));expect(onCombo).toHaveBeenCalledWith([1,2],1050);
});

it('hides expected stock during a physical count and records its branch and capture time',async()=>{
 api.get.mockImplementation(async(url:string)=>({data:url.endsWith('catalog')?{restaurant_id:202,user_id:1,stock:[{id:7,name:'Beef',unit:'kg',on_hand:999}]}:url.endsWith('bills')?{bills:[]}:[]}));
 api.post.mockResolvedValue({data:{message:'Count recorded',entry_id:3}});
 render(<StockEntries/>);await waitFor(()=>expect(screen.getByRole('button',{name:'Save stock or bill entry'})).toHaveProperty('disabled',false));
 expect(screen.queryByText('999')).toBeNull();fireEvent.change(screen.getByLabelText('Stock item'),{target:{value:'7'}});fireEvent.change(screen.getByLabelText('Stock quantity'),{target:{value:'8'}});fireEvent.change(screen.getByLabelText('Reason / shift reference'),{target:{value:'Evening shift'}});
 fireEvent.click(screen.getByRole('button',{name:'Save stock or bill entry'}));
 await screen.findByText('Count recorded');expect(api.post).toHaveBeenCalledWith('/api/v1/owner/operations/entries',expect.objectContaining({restaurant_id:202,kind:'count',quantity:8,captured_at:expect.any(String),entry_key:expect.any(String)}));
});
