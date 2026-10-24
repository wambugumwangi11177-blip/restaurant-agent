import { kes } from "@/lib/owner/format";
import ChartEmpty from "./ChartEmpty";

type Item = { item: string; unit: string; expected: number; used: number; missing: number; missingValue: number };

/** Used − what the recipes explain = what is missing, and what that is worth. */
export default function MissingFormula({ item }: { item: Item | null }) {
  if (!item) return <ChartEmpty state="no_data" reason="When a count and the recipes disagree, the gap and its value show up here." height={88} />;
  const n = (v: number) => String(Number(v.toFixed(2)));
  return (
    <figure aria-label={`${item.item} missing stock`}>
      <p className="text-sm leading-relaxed">
        <b>{item.item}</b>: used {n(item.used)} {item.unit} − recipes explain {n(item.expected)} {item.unit} = <b>{n(item.missing)} {item.unit}</b> missing, worth {kes(item.missingValue)}.
      </p>
      <svg role="img" aria-label="Missing stock as three bars" viewBox="0 0 320 72" className="mt-2 w-full">
        {[
          { label: "Recipes", value: item.expected, color: "var(--v-good)" },
          { label: "Used", value: item.used, color: "var(--v-primary)" },
          { label: "Missing", value: Math.max(item.missing, 0), color: "var(--v-destructive)" },
        ].map((bar, i) => {
          const max = Math.max(item.expected, item.used, item.missing, 0.01);
          const w = (bar.value / max) * 210;
          const y = 8 + i * 22;
          return (
            <g key={bar.label}>
              <text x="0" y={y + 10} fontSize="9" fill="var(--v-muted-foreground)">{bar.label}</text>
              <rect x="62" y={y} width={Math.max(w, bar.value > 0 ? 2 : 0)} height="12" rx="2" fill={bar.color} />
            </g>
          );
        })}
      </svg>
    </figure>
  );
}
