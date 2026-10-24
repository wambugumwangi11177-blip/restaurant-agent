import ChartEmpty from "./ChartEmpty";

type Props = { item: string; unit: string; left: number; reorder: number | null; par: number | null };

/** One item's level against its reorder line and, when you set one, its full-shelf line. */
export default function StockLevel({ item, unit, left, reorder, par }: Props) {
  if (left == null || Number.isNaN(left)) return <ChartEmpty state="no_data" reason="Stock levels will draw a line here once an item is on the shelf." />;
  const top = Math.max(left, reorder ?? 0, par ?? 0, 1) * 1.15;
  const y = (v: number) => 108 - (v / top) * 88;
  return (
    <figure>
      <svg role="img" aria-label={`${item}: ${left} ${unit} on hand`} viewBox="0 0 320 120" className="w-full">
        <line x1="24" x2="300" y1={y(0)} y2={y(0)} stroke="var(--v-border)" />
        <line x1="40" x2="280" y1={y(left)} y2={y(left)} stroke="var(--v-primary)" strokeWidth="2" />
        <circle cx="160" cy={y(left)} r="3.5" fill="var(--v-primary)" />
        {reorder != null && <line x1="24" x2="300" y1={y(reorder)} y2={y(reorder)} stroke="var(--v-warn)" strokeDasharray="4 3" />}
        {par != null && par > 0 && <line x1="24" x2="300" y1={y(par)} y2={y(par)} stroke="var(--v-good)" strokeDasharray="2 3" />}
        <text x="28" y="14" fontSize="9" fill="var(--v-muted-foreground)">{item}</text>
      </svg>
      <figcaption className="text-[11px] text-[var(--v-muted-foreground)]">
        {left} {unit} on hand{reorder != null ? ` · reorder at ${reorder} ${unit}` : ""}{par != null && par > 0 ? ` · full shelf ${par} ${unit}` : ""}.
      </figcaption>
    </figure>
  );
}
