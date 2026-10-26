import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import api from '@/lib/api';
import PriceSimulator from '@/components/owner/PriceSimulator';
vi.mock('@/lib/api',()=>({default:{get:vi.fn(),post:vi.fn()}}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
it('models the selected dish, displays assumptions and never saves a price',async()=>{
 vi.mocked(api.get).mockResolvedValue({data:{items:[{id:7,name:'Quarter chicken',price_kes:400}]}} as never);
 vi.mocked(api.post).mockResolvedValue({data:{state:'assumption',dish:'Quarter chicken',demand_change_pct:-7,elasticity:-0.7,sensitivity_source:'owner assumption',confidence_pct:65,rows:[{key:'sales',label:'Dish sales per 30 days',unit:'kes',before:4000,after:4092}],notes:['This does not save a menu price.']}} as never);
 render(<PriceSimulator/>);await screen.findByRole('option',{name:'Quarter chicken · KES 400'});
 fireEvent.change(screen.getByLabelText('Simulation dish'),{target:{value:'7'}});
 fireEvent.change(screen.getByLabelText('Simulation proposed price'),{target:{value:'440.10'}});
 fireEvent.submit(screen.getByRole('button',{name:'Model price & demand'}).closest('form')!);
 await screen.findByText('Quarter chicken · 30-day scenario');
 expect(api.post).toHaveBeenCalledExactlyOnceWith('/api/v1/owner/planning/price-simulation',{menu_item_id:7,new_price_cents:44010});
 expect(screen.getByText('This does not save a menu price.')).toBeTruthy();
});
