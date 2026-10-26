import {useState} from 'react';
import TierLayoutShell from '@/components/staff/TierLayoutShell';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import StockReview from '@/components/owner/StockReview';
import DailyStockWorkspace from '@/components/operations/DailyStockWorkspace';
import DailyWorkspace from '@/components/operations/DailyWorkspace';
import {kes,pct} from '@/lib/owner/format';
import api from '@/lib/api';
const auth=vi.hoisted(()=>({user:{id:7,role:'staff',staff_role:'waiter',tenant_name:'Demo Restaurant'}}));
vi.mock('@/context/AuthContext',()=>({useAuth:()=>({user:auth.user})}));
vi.mock('@/components/staff/AttendanceWidget',()=>({default:()=>null}));
vi.mock('@/components/NotificationBell',()=>({default:()=>null}));
vi.mock('next/navigation',()=>({useRouter:()=>({push:vi.fn()}),usePathname:()=>'/staff/waiter'}));
vi.mock('@/lib/api',()=>({default:{get:vi.fn(),post:vi.fn()}}));
beforeEach(()=>{window.history.replaceState({},'','/planning?tool=stock-review');vi.clearAllMocks();auth.user.staff_role='waiter';auth.user.id=7;});
afterEach(cleanup);
it('never formats absent money or percentages as zero',()=>{expect(kes(null)).toBe('Not recorded');expect(pct(undefined)).toBe('Not recorded');expect(kes(0)).toBe('KES 0');});
it('limits stock preview to five items and preserves search and pages in URL',async()=>{
 const items=Array.from({length:12},(_,i)=>({id:i+1,name:'Stock '+(i+1),unit:'kg',current_stock:2,value_kes:100,cost_missing:false,negative_book_stock:false,velocity:'slow',waste_pct:0,waste_qty_30d:0,abc_class:'A',count_due:'2026-10-25',count_overdue:true}));
 vi.mocked(api.get).mockResolvedValue({data:{value_kes:1200,note:'Recorded stock only',items,supplier_prices:[]}} as never);
 render(<StockReview/>);await screen.findByRole('heading',{name:'Stock 1'});expect(screen.getAllByRole('button',{name:'Open item →'})).toHaveLength(5);
 expect(screen.queryByRole('heading',{name:'Stock 6'})).toBeNull();fireEvent.click(screen.getByRole('button',{name:'Next'}));expect(screen.getByRole('heading',{name:'Stock 6'})).toBeTruthy();expect(window.location.search).toContain('page=2');
 fireEvent.change(screen.getByLabelText('Search stock'),{target:{value:'Stock 12'}});expect(screen.getByRole('heading',{name:'Stock 12'})).toBeTruthy();expect(window.location.search).toContain('stockSearch=Stock+12');expect(window.location.search).not.toContain('page=2');
});
it('waiter sees assigned blind count without expected cash or accounting review',async()=>{
 vi.mocked(api.get).mockResolvedValue({data:{day:'2026-10-25',role:'waiter',identity:7,pending_handovers:0,disputed_handovers:0,close_status:'open',assignments:[{user_id:7,start:'2026-10-25T05:00:00',end:'2026-10-25T13:00:00'}]}} as never);
 render(<DailyWorkspace/>);await screen.findByLabelText('Assigned cash physically counted');expect(screen.queryByText(/Cash expected:/)).toBeNull();expect(screen.queryByRole('heading',{name:'Day-close review'})).toBeNull();
});

it('staff stock records use five-item server pages and retain search in the URL',async()=>{
 const all=Array.from({length:12},(_,i)=>({id:i+1,name:'Ingredient '+(i+1),unit:'kg',on_hand:2,needs_location_review:i===0}));
 vi.mocked(api.get).mockImplementation(async(_path,options)=>{const params=(options?.params??{}) as {q?:string;page?:number};const q=params.q??'';const page=params.page??1;const filtered=all.filter(i=>i.name.includes(q));return {data:{as_of:'2026-10-25T09:00:00Z',total:filtered.length,page,pages:Math.max(1,Math.ceil(filtered.length/5)),items:filtered.slice((page-1)*5,page*5)}} as never;});
 render(<DailyStockWorkspace/>);await screen.findByRole('heading',{name:'Ingredient 1'});expect(screen.getAllByRole('button',{name:'Count or record waste →'})).toHaveLength(5);
 fireEvent.click(screen.getByRole('button',{name:'Next'}));await screen.findByRole('heading',{name:'Ingredient 6'});expect(window.location.search).toContain('page=2');
 fireEvent.change(screen.getByLabelText('Find stock to record'),{target:{value:'Ingredient 12'}});await screen.findByRole('heading',{name:'Ingredient 12'});expect(window.location.search).toContain('stockSearch=Ingredient+12');expect(window.location.search).not.toContain('page=2');
});

it('personal identity switching resets staff drafts even when both people have the same role',()=>{
 function PersonalDraft(){const [value,setValue]=useState('');return <input aria-label="Personal draft" value={value} onChange={e=>setValue(e.target.value)}/>;}
 const content=()=> <TierLayoutShell tier="waiter" tierLabel="Waiter" navItems={[]}><PersonalDraft/></TierLayoutShell>;
 const view=render(content());fireEvent.change(screen.getByLabelText('Personal draft'),{target:{value:'Previous person unsaved record'}});auth.user.id=8;view.rerender(content());expect(screen.getByLabelText('Personal draft')).toHaveProperty('value','');
});
