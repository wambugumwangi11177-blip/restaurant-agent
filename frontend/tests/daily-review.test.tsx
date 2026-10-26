import {afterEach,expect,it,vi} from 'vitest';
import {act,cleanup,render,screen,fireEvent} from '@testing-library/react';
import {useState} from 'react';
import {useDailyReview} from '@/lib/owner/useDailyReview';
function Probe(){const day=useDailyReview();const [draft,setDraft]=useState('');return <><output>{day}</output><input aria-label="Unsaved quantity" value={draft} onChange={e=>setDraft(e.target.value)}/></>;}
afterEach(()=>{cleanup();vi.useRealTimers();});
it('advances at Nairobi midnight without discarding an unsaved input',()=>{vi.useFakeTimers();vi.setSystemTime(new Date('2026-10-25T20:59:30Z'));render(<Probe/>);expect(screen.getByText('2026-10-25')).toBeTruthy();fireEvent.change(screen.getByLabelText('Unsaved quantity'),{target:{value:'2.75'}});act(()=>vi.advanceTimersByTime(60000));expect(screen.getByText('2026-10-26')).toBeTruthy();expect((screen.getByLabelText('Unsaved quantity') as HTMLInputElement).value).toBe('2.75');});
it('refreshes a sleeping tab on focus when its review day has changed',()=>{vi.useFakeTimers();vi.setSystemTime(new Date('2026-10-25T18:00:00Z'));render(<Probe/>);vi.setSystemTime(new Date('2026-10-26T07:00:00Z'));fireEvent(window,new Event('focus'));expect(screen.getByText('2026-10-26')).toBeTruthy();});
