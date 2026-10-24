"use client";
import { kes } from "@/lib/owner/format";
import type { Health, HealthStatus } from "@/lib/owner/types";
import StateChip from "@/components/owner/StateChip";

const DOT: Record<HealthStatus, string> = {
  good: "bg-[var(--v-good)]", watch: "bg-[var(--v-warn)]", bad: "bg-[var(--v-destructive)]", unknown: "bg-[var(--v-border)]",
};

function value(number: number | null, unit: string): string {
  if (number == null) return "Not set up";
  return unit === "KES" ? kes(number) : unit === "%" ? `${Number(number.toFixed(1))}%` : unit === "days" ? `${number} days` : String(number);
}

/** Six tiles, one per area: one number, one word, one colour. A tile jumps to its panel below. */
export default function HealthStrip({ health }: { health: Health }) {
  if (health.tiles.length === 0) return <p className="text-xs text-[var(--v-muted-foreground)]">{health.reason ?? "Nothing to summarise yet."}</p>;
  return (
    <ul className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      {health.tiles.map((t) => (
        <li key={t.area}>
          <a href={`#area-${t.area}`} className="block h-full rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-3 hover:border-[var(--v-primary)]">
            <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--v-muted-foreground)]">
              <span aria-hidden className={`h-2 w-2 rounded-full ${DOT[t.status]}`} />{t.title}
            </p>
            <p className="font-display mt-2 text-xl font-semibold tracking-[-0.03em]">{value(t.number, t.unit)}</p>
            {t.number != null && <p className="mt-0.5 text-[11px] font-semibold">{t.word}</p>}
            <p className="mt-0.5 text-[10px] leading-snug text-[var(--v-muted-foreground)]">{t.label}</p>
            {t.rule && (
              <details className="mt-1">
                <summary className="cursor-pointer text-[10px] font-semibold text-[var(--v-primary)]">Why?</summary>
                <p className="mt-0.5 text-[10px] leading-snug text-[var(--v-muted-foreground)]">{t.rule}</p>
              </details>
            )}
            {t.state && <StateChip block={{...t, state:t.state}} className="mt-1" />}
          </a>
        </li>
      ))}
    </ul>
  );
}
