"use client";
import StateChip from "@/components/owner/StateChip";
import { BLOCK_TITLES } from "@/lib/owner/blocks";
import type { Area, AreaKey } from "@/lib/owner/types";
import CashArea from "./areas/CashArea";
import MoneyArea from "./areas/MoneyArea";
import PermitsArea from "./areas/PermitsArea";
import SalesArea from "./areas/SalesArea";
import StaffArea from "./areas/StaffArea";
import StoreArea from "./areas/StoreArea";

const AREAS: Record<AreaKey, (props: { area: Area }) => React.JSX.Element> = {
  money: MoneyArea, sales_dishes: SalesArea, store: StoreArea, cash: CashArea, staff: StaffArea, permits: PermitsArea,
};

/** What an area panel holds when it opens: every block of the area, drawn for what it is. */
export default function AreaBody({ area }: { area: Area }) {
  const Body = AREAS[area.key];
  if (Body) return <Body area={area} />;
  // A block we have no drawing for still says what it is and why it is empty, so a new block can never silently vanish.
  const titles = BLOCK_TITLES[area.key] ?? {};
  return (
    <ul className="space-y-2">
      {Object.entries(area.blocks).map(([key, block]) => (
        <li key={key} className="flex flex-wrap items-center gap-2 text-xs"><span className="font-semibold">{titles[key] ?? key}</span><StateChip block={block} />{block.reason && <span>{String(block.reason)}</span>}</li>
      ))}
    </ul>
  );
}
