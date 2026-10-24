"use client";
/**
 * The creative layer's note, kept apart from the computed figures.
 * The label says it was written by the model. When that write fails, the
 * figures above stay and this shows only the short unavailable line.
 */
import type { Insight } from "@/lib/owner/types";

export default function InsightNote({ insight }: { insight?: Insight | null }) {
  if (!insight) return null;
  const text = insight.state === "live" ? insight.text : null;
  const note = insight.state === "unavailable" ? insight.note : null;
  if (!text && !note) return null;
  return (
    <section
      aria-label={insight.label}
      className="rounded-xl border border-[hsl(43_76%_57%_/_0.45)] bg-[hsl(42_71%_75%_/_0.16)] p-4"
    >
      <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--v-muted-foreground)]">{insight.label}</p>
      {text && <p className="mt-2 whitespace-pre-wrap text-[13px] leading-relaxed">{text}</p>}
      {note && <p role="status" className="mt-2 text-sm text-[var(--v-muted-foreground)]">{note}</p>}
    </section>
  );
}
