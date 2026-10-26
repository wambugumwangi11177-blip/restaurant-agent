import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,render,screen,waitFor} from '@testing-library/react';
import StockTool from '@/components/owner/StockTool';
import GrowthTools from '@/components/owner/GrowthTools';
import EntryWorkspace from '@/components/operations/EntryWorkspace';
import {FEATURE_GROUPS} from '@/lib/owner/features';
import api from '@/lib/api';
vi.mock('@/lib/api',()=>({default:{get:vi.fn(),post:vi.fn(),put:vi.fn()}}));
vi.mock('@/context/AuthContext',()=>({useAuth:()=>({user:{id:1,role:'admin',staff_role:'owner',tenant_name:'Demo Restaurant'},isLoading:false})}));
const stock={as_of:'2026-10-26T07:00:00',entered_up_to:'2026-10-25',value_kes:9876,note:'Saved unit costs, missing costs excluded',items:[{id:1,name:'Beef',unit:'kg',current_stock:12,value_kes:9876,cost_missing:false,negative_book_stock:false,velocity:'slow',spoilage_risk:75,spoilage_window:null,waste_pct:5,waste_qty_30d:0.25,abc_class:'A',count_due:'2026-10-26',count_overdue:true,count_calendar:['2026-10-26','2026-10-27']}],supplier_prices:[{item:'Beef',supplier:'Test Butcher',unit:'kg',first_kes:100,latest_kes:120,change_pct:20,deliveries:3}]};
beforeEach(()=>{vi.clearAllMocks();window.history.replaceState({},'','/planning');vi.mocked(api.get).mockImplementation(async(url)=>({data:String(url).includes('stock-review')?stock:String(url).includes('menu-review')?{state:'as_entered',note:'Recorded menu sales',items:[],gaps:[{from_kes:300,to_kes:900,gap_kes:600}],tail_ingredients:4,combos:[],results:[]}:String(url).includes('catalog')?{restaurant_id:1,stock:[],dishes:[]}:String(url).includes('categories')?{categories:[]}:[]} as never));});
afterEach(cleanup);
it('every distinct directory tool has its own destination; combined overview is not a tool',()=>{const tools=FEATURE_GROUPS.flatMap(g=>g.items);expect(new Set(tools.map(t=>t.href)).size).toBe(tools.length);expect(tools.some(t=>t.href.includes('ingredients-and-wages'))).toBe(false);expect(tools.some(t=>t.href.endsWith('menu-growth')||t.href.endsWith('stock-review'))).toBe(false);});
it.each([
 ['stock-value','KES 9,876','0.25 kg written off'],
 ['recorded-waste','0.25 kg written off','KES 9,876'],
 ['abc-counts','Class A · next count 2026-10-26','KES 9,876'],
 ['supplier-prices','KES 100.00 → KES 120.00 per kg','0.25 kg written off'],
 ['stock-movement','Movement: slow','KES 9,876'],
 ['expiry-risk','Estimated risk 75.0%','0.25 kg written off'],
] as const)('%s shows its own measure and does not repeat a stock dashboard',async(view,value,unrelated)=>{render(<StockTool view={view}/>);await screen.findByText('Beef',{exact:false});expect(document.body.textContent).toContain(value);expect(document.body.textContent).not.toContain(unrelated);expect(api.get).toHaveBeenCalledWith('/api/v1/owner/planning/stock-review');});
it.each(['price-ladder','menu-tail','scheduled-prices','price-learning','combo-candidates'])('%s mounts only its own menu tool',async(view)=>{render(<GrowthTools view={view} onCombo={()=>{}}/>);await waitFor(()=>expect(document.querySelectorAll('section > details')).toHaveLength(1));expect(document.querySelectorAll('section > details')).toHaveLength(1);if(view!=='scheduled-prices')expect(screen.queryByRole('button',{name:'Save scheduled price'})).toBeNull();if(view==='price-ladder')expect(document.body.textContent).toContain('Gap KES 600');});
it('a delivery link opens the actual delivery inputs and no expense or accounting dashboard',async()=>{window.history.replaceState({},'','/entries?tool=delivery');render(<EntryWorkspace/>);await screen.findByLabelText('Expected delivery');expect(screen.queryByLabelText('Amount (KES)')).toBeNull();expect(screen.queryByRole('heading',{name:'Accounting review & corrections'})).toBeNull();expect(screen.queryByRole('navigation',{name:'Entry types'})).toBeNull();});
it('the area directory is a choice, never an aggregate view',()=>{window.history.replaceState({},'','/entries');render(<EntryWorkspace/>);expect(screen.getByRole('heading',{name:'Choose one entry task'})).toBeTruthy();expect(screen.getByRole('link',{name:'Receive a delivery →'}).getAttribute('href')).toBe('/entries?tool=delivery');expect(screen.queryByLabelText('Amount (KES)')).toBeNull();});
