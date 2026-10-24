import ChartEmpty from "./ChartEmpty";

type Gap = { item: string; unit: string; store: number; kitchen: number };

/** Two places stock can sit: the store, then the kitchen. A gap is a handover the two counts did not agree on. */
export default function CustodyZones({ gaps, label = "Store and kitchen" }: { gaps: Gap[]; label?: string }) {
  return (
    <figure>
      <svg role="img" aria-label={label} viewBox="0 0 320 88" className="w-full">
        <rect x="8" y="16" width="130" height="56" rx="8" fill="none" stroke="var(--v-primary)" />
        <rect x="182" y="16" width="130" height="56" rx="8" fill="none" stroke="var(--v-sidebar-primary)" />
        <text x="73" y="36" textAnchor="middle" fontSize="10" fontWeight="700" fill="var(--v-foreground)">Store</text>
        <text x="247" y="36" textAnchor="middle" fontSize="10" fontWeight="700" fill="var(--v-foreground)">Kitchen</text>
        <text x="73" y="54" textAnchor="middle" fontSize="8" fill="var(--v-muted-foreground)">Received and counted</text>
        <text x="247" y="54" textAnchor="middle" fontSize="8" fill="var(--v-muted-foreground)">Counted blind</text>
        <path d="M138 44 H182" stroke="var(--v-border)" />
        <path d="M174 40 L182 44 L174 48" fill="var(--v-border)" />
      </svg>
      {gaps.length === 0
        ? <figcaption className="text-[11px] text-[var(--v-muted-foreground)]">No handover disagreed in this period. A disputed count will name the item and both quantities here.</figcaption>
        : <ul className="mt-1 space-y-1 text-[11px]">{gaps.map((g) => <li key={g.item}><b>{g.item}</b>: store {g.store} {g.unit}, kitchen counted {g.kitchen} {g.unit}.</li>)}</ul>}
    </figure>
  );
}
