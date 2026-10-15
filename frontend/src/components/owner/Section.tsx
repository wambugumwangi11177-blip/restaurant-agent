import type { ReactNode } from "react";

/** A Home zone: a small caps eyebrow, a display heading, an optional right-hand note. */
export default function Section({ id, eyebrow, title, meta, children }: { id?: string; eyebrow: string; title: string; meta?: ReactNode; children: ReactNode }) {
  const heading = id ? `${id}-heading` : undefined;
  return (
    <section id={id} aria-labelledby={heading} className="scroll-mt-4">
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <p className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--v-muted-foreground)]">{eyebrow}</p>
          <h2 id={heading} className="font-display text-2xl font-semibold tracking-[-0.035em]">{title}</h2>
        </div>
        {meta && <div className="text-[11px] text-[var(--v-muted-foreground)]">{meta}</div>}
      </div>
      {children}
    </section>
  );
}
