import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import QuickSwitchModal from '@/components/QuickSwitchModal';
import POSWorkspace from '@/components/features/pos/POSWorkspace';
import api from '@/lib/api';
vi.mock('@/lib/api',()=>({default:{get:vi.fn(),post:vi.fn()}}));
vi.mock('@/context/AuthContext',()=>({useAuth:()=>({loginWithPin:vi.fn()})}));
vi.mock('@/lib/offlineOrderOutbox',()=>({getPendingOrders:async()=>[],replayPendingOrders:async()=>({sent:0}),queueOrder:vi.fn(),isNetworkFailure:()=>false}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
it('does not claim no PIN users when the roster cannot be read, and retries',async()=>{
 vi.mocked(api.get).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({data:[{user_id:11,name:'Demo Accountant',role_title:'Accountant'}]} as never);
 render(<QuickSwitchModal onClose={()=>{}} onSetUpOwnPin={()=>{}}/>);
 await screen.findByRole('alert');expect(screen.queryByText(/No teammates have set up/)).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Retry roster'}));await screen.findByRole('button',{name:/Demo Accountant/});
});
it('a failed menu read is retryable and never described as an empty branch',async()=>{
 vi.mocked(api.get).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({data:[{id:1,name:'Daily stew',price:30000,category:'Meals',is_available:true}]} as never);
 render(<POSWorkspace/>);await screen.findByRole('alert');expect(screen.queryByText(/No available dishes recorded/)).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Retry menu'}));await screen.findByRole('button',{name:/Daily stew/});
});
