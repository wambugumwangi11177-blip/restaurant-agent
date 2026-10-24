import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import TeamWork from '@/app/team-work/page';
import Setup from '@/app/(owner)/setup/page';
const api=vi.hoisted(()=>({get:vi.fn(),post:vi.fn()}));
const state=vi.hoisted(()=>({user:{id:1,role:'admin',staff_role:'owner'}}));
vi.mock('@/lib/api',()=>({default:api}));
vi.mock('@/context/AuthContext',()=>({useAuth:()=>({...state,isLoading:false})}));
afterEach(cleanup);
beforeEach(()=>{vi.clearAllMocks();state.user={id:1,role:'admin',staff_role:'owner'};api.post.mockResolvedValue({data:{}});api.get.mockImplementation(async(url:string)=>({data:url.endsWith('/activity')?{items:[]}:url.endsWith('/people')?{items:[{id:2,name:'Chef'}]}:url.endsWith('/options')?{stock:[],expenses:[]}:{restaurant_id:202,items:[]}}));});
it('submits a delegated task with branch and retry key',async()=>{
 render(<TeamWork/>);await screen.findByRole('option',{name:'Chef'});
 fireEvent.change(screen.getByLabelText('Title'),{target:{value:'Check the delivery'}});
 fireEvent.change(screen.getByLabelText('Reason and evidence'),{target:{value:'Compare the supplier invoice'}});
 fireEvent.change(screen.getByLabelText('Assign to'),{target:{value:'2'}});
 fireEvent.click(screen.getByRole('button',{name:'Save request'}));
 await waitFor(()=>expect(api.post).toHaveBeenCalledWith('/api/v1/team-work',expect.objectContaining({restaurant_id:202,assigned_to:2,kind:'task',request_key:expect.any(String)})));
});
it('requires a review note before approving and sends the displayed revision',async()=>{
 api.get.mockImplementation(async(url:string)=>({data:url.endsWith('/activity')?{items:[]}:url.endsWith('/people')?{items:[]}:url.endsWith('/options')?{stock:[],expenses:[]}:{restaurant_id:202,items:[{id:8,kind:'expense_void',title:'Duplicate receipt',status:'pending',revision:3,created_by:2,details:{request:{reason:'Same invoice entered twice',expense_id:7}}}]}}));
 render(<TeamWork/>);const button=await screen.findByRole('button',{name:'Approve'});expect((button as HTMLButtonElement).disabled).toBe(true);
 fireEvent.change(screen.getByLabelText('Review or completion note'),{target:{value:'Verified both receipts'}});fireEvent.click(button);
 await waitFor(()=>expect(api.post).toHaveBeenCalledWith('/api/v1/team-work/8/transition',{revision:3,action:'approve',note:'Verified both receipts'}));
});
it('resumes setup and records an owner review without claiming a live connection',async()=>{
 api.get.mockResolvedValue({data:{restaurant_id:202,notice:'Reviews do not certify integration.',steps:[{key:'source',title:'Verify the till',count:0,detail:'A real source sample is needed.',href:'/home',review:null}]}});
 render(<Setup/>);await screen.findByText('Verify the till',{selector:'h2'});
 fireEvent.change(screen.getByLabelText('What did you verify, and with whom?'),{target:{value:'Reviewed sample totals with Sam'}});fireEvent.click(screen.getByRole('button',{name:'Save review and continue'}));
 await waitFor(()=>expect(api.post).toHaveBeenCalledWith('/api/v1/owner/setup/source/review',{restaurant_id:202,note:'Reviewed sample totals with Sam'}));
 expect(screen.getByText('Reviews do not certify integration.')).toBeTruthy();
});
