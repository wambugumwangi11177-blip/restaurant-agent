"use client";
import Dial from "@/components/charts/Dial";
import HBars from "@/components/charts/HBars";
import { BLOCK_TITLES } from "@/lib/owner/blocks";
import { kes } from "@/lib/owner/format";
import type { KitchenBlock, OnShiftBlock, WagesBlock } from "@/lib/owner/areaTypes";
import type { Area } from "@/lib/owner/types";
import { BlockFrame, Empty, Grid, Note, Stat } from "./ui";

const T = BLOCK_TITLES.staff;

export default function StaffArea({ area }: { area: Area }) {
  const b = area.blocks;
  return (
    <div className="space-y-3">
      <Wages block={b.wages as WagesBlock} />
      <div className="grid gap-3 md:grid-cols-2">
        <OnShift block={b.on_shift as OnShiftBlock} />
        <Kitchen block={b.kitchen as KitchenBlock} />
      </div>
    </div>
  );
}

function Wages({ block }: { block: WagesBlock }) {
  const target = block.assumption?.value ?? 30;
  return (
    <BlockFrame title={T.wages} block={block}>{() => (<>
      <div className="grid gap-4 md:grid-cols-[14rem_1fr]">
        <Dial value={block.wages_pct} target={target} label="Out of every KES 100, wages" word={block.word} tone={block.word === "Fine" ? "good" : "bad"} />
        <div>
          <Grid cols={3}>
            <Stat label="Wages, last 30 days" value={kes(block.wages_30d)} />
            <Stat label="Sales per staff hour" value={kes(block.sales_per_staff_hour)} />
            <Stat label="Overtime" value={`${block.overtime_hours} h`} note={block.overtime_cost ? `cost ${kes(block.overtime_cost)}` : "none to pay extra for"} />
          </Grid>
          {block.by_person.length > 0 && <div className="mt-4"><HBars label="Wages by person, last 30 days" rows={block.by_person.map((p) => ({ key: p.name, label: p.name, value: p.wages, valueLabel: kes(p.wages), note: `${p.hours} hours` }))} /></div>}
        </div>
      </div>
    </>)}</BlockFrame>
  );
}

function OnShift({ block }: { block: OnShiftBlock }) {
  return (
    <BlockFrame title={T.on_shift} block={block}>{() => (<>
      <Grid cols={2}><Stat label="On shift now" value={block.on_shift} /><Stat label="Scheduled today" value={block.scheduled} /></Grid>
    </>)}</BlockFrame>
  );
}

function Kitchen({ block }: { block: KitchenBlock }) {
  return (
    <BlockFrame title={T.kitchen} block={block}>{() => (<>
      {block.stations.length === 0 ? <Empty>No tickets recorded yet.</Empty> : (
        <HBars label="Average minutes to prepare, by station" rows={block.stations.map((s) => ({ key: s.station, label: s.station.charAt(0).toUpperCase() + s.station.slice(1), value: s.avg_minutes, valueLabel: `${s.avg_minutes} min`, flag: block.slowest[0]?.station === s.station }))} />
      )}
      {block.slowest.length > 0 && <Note>Slowest against its own usual: {block.slowest.map((s) => `${s.station} (${Math.round(s.minutes_over_average)} min over)`).join(", ")}.</Note>}
    </>)}</BlockFrame>
  );
}
