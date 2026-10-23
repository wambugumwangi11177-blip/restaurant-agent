import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import StockReview from '@/components/owner/StockReview';
const api = vi.hoisted(()=>({get:vi.fn()}));
vi.mock('@/lib/api',()=>({default:api}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
it('shows unknown costs and negative stock as actions, with a scheduled count',async()=>{
 api.get.mockResolvedValue({data:{value_kes:0,note:'Recorded entries only',items:[{id:1,name:'Beef',unit:'kg',current_stock:-2,value_kes:0,cost_missing:true,negative_book_stock:true,velocity:'slow',waste_pct:40,waste_qty_30d:.2,abc_class:'A',count_due:'2026-10-23',count_overdue:true}],supplier_prices:[]}});
 render(<StockReview/>);
 expect(await screen.findByText('Cost missing')).toBeTruthy();
 expect(screen.getByText(/reconcile negative stock/)).toBeTruthy();
 expect(screen.getByText('40% (0.2 kg)')).toBeTruthy();
 expect(screen.getByText('2026-10-23 · Due')).toBeTruthy();
 expect(screen.getByText(/Two delivered purchases/)).toBeTruthy();
});
it('shows a failed request without inventing empty stock',async()=>{
 api.get.mockRejectedValue(new Error('offline'));render(<StockReview/>);
 expect((await screen.findByRole('alert')).textContent).toContain('Could not load stock review');
 expect(screen.queryByText(/Book stock:/)).toBeNull();
});
