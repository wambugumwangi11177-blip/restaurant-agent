import { kes } from "@/lib/owner/format";
import ChartEmpty from "./ChartEmpty";

export type Tender = { key: string; label: string; kes: number };

const COLORS = ["var(--v-primary)", "var(--v-sidebar-primary)", "var(--v-good)", "var(--v-muted-foreground)"];

/** How today's paid sales split across cash, M-Pesa and card. */
export default function TenderMix({ tenders, label = "How today's sales were paid" }: { tenders: Tender[]; label?: string }) {
  const rows = tenders.filter((t) => t.kes > 0);
  const total = rows.reduce((s, t) => s + t.kes, 0);
  if (total <= 0) return <ChartEmpty state="no_data" reason="Paid sales today will split into cash, M-Pesa and card once an order is taken." height={72} />;
  return (
    <figure>
      <svg role="img" aria-label={label} viewBox="0 0 320 36" className="w-full">
        {(() => {
          let x = 0;
          return rows.map((t, i) => {
            const w = (t.kes / total) * 320;
            const node = <rect key={t.key} x={x} y={4} width={Math.max(w, 1)} height={18} fill={COLORS[i % COLORS.length]}><title>{t.label}: {kes(t.kes)}</title></rect>;
            x += w;
            return node;
          });
        })()}
      </svg>
      <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px]">
        {rows.map((t, i) => (
          <li key={t.key} className="inline-flex items-center gap-1.5">
            <span aria-hidden className="h-2 w-2 rounded-sm" style={{ background: COLORS[i % COLORS.length] }} />
            {t.label} {kes(t.kes)} · {Math.round((t.kes / total) * 100)}%
          </li>
        ))}
      </ul>
    </figure>
  );
}
