import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import EntryWorkspace,{cents} from '@/components/operations/EntryWorkspace';
import PlanningWorkspace from '@/components/owner/PlanningWorkspace';
import api from '@/lib/api';
const account=vi.hoisted(()=>({role:'admin',staff_role:'owner',tenant_name:'Demo Restaurant',id:1}));
const navigation=vi.hoisted(()=>({query:''}));
vi.mock('next/navigation',()=>({useRouter:()=>({push:vi.fn()}),useSearchParams:()=>new URLSearchParams(navigation.query)}));
vi.mock('@/context/AuthContext',()=>({useAuth:()=>({user:account,isLoading:false})}));
vi.mock('@/lib/api',()=>({default:{get:vi.fn(),post:vi.fn(),put:vi.fn()}}));
beforeEach(()=>{window.history.replaceState({},'','/entries?tool=expense');navigation.query='';vi.clearAllMocks();account.role='admin';account.staff_role='owner';vi.mocked(api.get).mockImplementation(async(path)=>({data:String(path).includes('/catalog')?{restaurant_id:202,user_id:1,stock:[],dishes:[{id:1,name:'Fish'},{id:2,name:'Stew'}]}:String(path).includes('/categories')?{categories:[{key:'gas',name:'Cooking gas'}]}:String(path).includes('/planning/stock-review')?{value_kes:0,note:'Recorded entries only',items:[],supplier_prices:[]}:String(path).includes('/planning/menu-review')?{state:'no_data',note:'No sales yet',items:[],gaps:[],tail_ingredients:0,combos:[],results:[]}:String(path).includes('/planning/shifts')?{shifts:[],note:'Not inferred from a weekly total.'}:[]}) as never);});
afterEach(cleanup);
it('parses decimal shillings exactly and refuses fractional cents',()=>{expect(cents('4500.10')).toBe(450010);expect(cents('0.01')).toBe(1);expect(()=>cents('1.001')).toThrow();expect(()=>cents('-2')).toThrow();});
it('saves an expense to the existing ledger and shows confirmation',async()=>{
 vi.mocked(api.post).mockResolvedValue({data:{id:1}} as never);render(<EntryWorkspace/>);
 await screen.findByText('Cooking gas');fireEvent.change(screen.getByLabelText('Cost category'),{target:{value:'gas'}});fireEvent.change(screen.getByLabelText('Amount (KES)'),{target:{value:'4500.10'}});fireEvent.click(screen.getByRole('button',{name:'Save expense'}));
 expect(await screen.findByRole('status')).toHaveProperty('textContent',expect.stringContaining('included in Profit'));
 expect(api.post).toHaveBeenCalledWith('/api/v1/owner/money/expenses',expect.objectContaining({amount_kes:'4500.10',category:'gas',entry_key:expect.any(String)}));
});
it('does not reveal expected cash before the count is submitted',async()=>{window.history.replaceState({},'','/entries?tool=cash');render(<EntryWorkspace/>);expect(screen.getByLabelText('Cash physically counted (KES)')).toBeTruthy();expect(screen.queryByText(/Cash expected:/)).toBeNull();expect(api.post).not.toHaveBeenCalled();});
it('stockkeepers get delivery entry rather than owner money controls',async()=>{account.role='staff';account.staff_role='stockkeeper';window.history.replaceState({},'','/entries?tool=delivery');render(<EntryWorkspace/>);await waitFor(()=>expect(api.get).toHaveBeenCalled());expect(screen.getByRole('heading',{name:'Receive a delivery'})).toBeTruthy();expect(screen.queryByRole('button',{name:'Expense'})).toBeNull();expect(screen.queryByRole('button',{name:'Close shift'})).toBeNull();});
it('kitchen accounts cannot access the entry tools',()=>{account.role='staff';account.staff_role='kitchen';render(<EntryWorkspace/>);expect(screen.getByRole('alert').textContent).toContain('cannot record');expect(api.get).not.toHaveBeenCalled();});
it('starts planning with task choices instead of every numerical workspace',()=>{render(<PlanningWorkspace/>);expect(screen.getByRole('link',{name:'Forecast-led prep & buying →'})).toBeTruthy();expect(screen.queryByRole('heading',{name:'Recipe yield & prep plan'})).toBeNull();expect(screen.queryByRole('heading',{name:'Shift report',level:2})).toBeNull();expect(api.get).not.toHaveBeenCalled();});

it('opens a combo tool without repeating recipe, shift and stock dashboards',async()=>{navigation.query='tool=combo-checker';render(<PlanningWorkspace/>);await screen.findByRole('heading',{name:'Combo checker',level:2});expect(screen.queryByRole('heading',{name:'Recipe yield & prep plan'})).toBeNull();expect(screen.queryByRole('heading',{name:'Shift report',level:2})).toBeNull();expect(screen.queryByRole('heading',{name:'Stock value & counting plan'})).toBeNull();expect(api.get).not.toHaveBeenCalledWith('/api/v1/owner/planning/stock-review');});
