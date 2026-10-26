import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen, fireEvent } from '@testing-library/react';
const nav=vi.hoisted(()=>({query:''}));
vi.mock('next/navigation',()=>({useSearchParams:()=>new URLSearchParams(nav.query)}));
import { legacyTool, toolHref, useToolSelection } from '@/lib/owner/useToolSelection';
function Probe(){return <output data-testid="tool">{useToolSelection()}</output>;}
beforeEach(()=>{nav.query='';window.history.replaceState({},'', '/');});
afterEach(cleanup);
it('recovers the last selection from the exact reported broken URL',()=>{expect(legacyTool('#ingredients-and-wages#costs-covered')).toBe('costs-covered');expect(legacyTool('#ingredients-and-wages%23costs-covered')).toBe('costs-covered');});
it('replaces the selected tool with an absolute path and one query',()=>{expect(toolHref('/areas/money','costs-covered')).toBe('/areas/money?tool=costs-covered');expect(toolHref('/areas/money','')).toBe('/areas/money');});
it('prefers a canonical tool over an obsolete fragment',()=>{window.history.replaceState({},'', '/areas/money#ingredients-and-wages#costs-covered');nav.query='tool=bills-coming-up';render(<Probe/>);expect(screen.getByTestId('tool').textContent).toBe('bills-coming-up');});
it('updates legacy selections and supports back navigation',()=>{window.history.replaceState({},'', '/areas/money#ingredients-and-wages');render(<Probe/>);expect(screen.getByTestId('tool').textContent).toBe('ingredients-and-wages');window.history.replaceState({},'', '/areas/money#costs-covered');fireEvent(window,new PopStateEvent('popstate'));expect(screen.getByTestId('tool').textContent).toBe('costs-covered');});
