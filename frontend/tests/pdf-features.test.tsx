import {expect,it} from "vitest";
import {FEATURE_GROUPS,blockAnchor} from "@/lib/owner/features";
import {BLOCK_TITLES} from "@/lib/owner/blocks";
it("every linked area figure has a real section anchor",()=>{for(const group of FEATURE_GROUPS){const anchors=Object.values(BLOCK_TITLES[group.area]).map(blockAnchor);for(const item of group.items){if(item.href.startsWith(`/areas/${group.area}?tool=`)){const id=new URL(item.href,'http://localhost').searchParams.get('tool');expect([...anchors,'price-impact','best-and-weakest-hours','unusual-sales-days','source-readiness','sales-per-staff-hour','overtime']).toContain(id);}}}});
it("the guide exposes its operational tools through reachable owner routes",()=>{const links=FEATURE_GROUPS.flatMap(g=>g.items.map(i=>i.href));expect(links).toContain('/purchasing?tool=approval');expect(links).toContain('/inventory');expect(links).toContain('/menu');expect(links.every(h=>!h.startsWith('/dashboard'))).toBe(true);expect(FEATURE_GROUPS).toHaveLength(6);});

it('tool links never rely on relative or stacked fragments',()=>{for(const g of FEATURE_GROUPS)for(const i of g.items){expect(i.href.startsWith('/')).toBe(true);expect(i.href).not.toContain('#');}});

it('every backed area block is directly discoverable',()=>{for(const g of FEATURE_GROUPS){const links=g.items.map(i=>i.href);for(const title of Object.values(BLOCK_TITLES[g.area]).filter(t=>t!=="Ingredients and wages"))expect(links).toContain(`/areas/${g.area}?tool=${blockAnchor(title)}`);}});
