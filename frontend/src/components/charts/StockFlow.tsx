const STEPS = [
  { key: "bought", label: "Bought" },
  { key: "received", label: "Received" },
  { key: "stored", label: "Stored" },
  { key: "issued", label: "Issued" },
  { key: "sold", label: "Sold" },
  { key: "counted", label: "Counted" },
];

/** The six steps stock takes, and where a leak can hide between sold and counted. */
export default function StockFlow({ leaks, label = "Where stock can leak" }: { leaks: number; label?: string }) {
  return (
    <figure>
      <svg role="img" aria-label={label} viewBox="0 0 320 78" className="w-full">
        {STEPS.map((s, i) => {
          const x = 8 + i * 52;
          const hot = s.key === "counted" && leaks > 0;
          return (
            <g key={s.key}>
              {i > 0 && <line x1={x - 10} x2={x} y1="28" y2="28" stroke="var(--v-border)" />}
              <rect x={x} y="12" width="42" height="32" rx="6" fill={hot ? "hsl(4 61% 52% / 0.12)" : "var(--v-muted)"} stroke={hot ? "var(--v-destructive)" : "var(--v-border)"} />
              <text x={x + 21} y="32" textAnchor="middle" fontSize="7.5" fill="var(--v-foreground)">{s.label}</text>
            </g>
          );
        })}
      </svg>
      <figcaption className="text-[11px] text-[var(--v-muted-foreground)]">
        {leaks > 0 ? `${leaks} item${leaks === 1 ? "" : "s"} used more than the recipes explain, between Sold and Counted.` : "Nothing is leaking between what you sold and what you counted."}
      </figcaption>
    </figure>
  );
}
