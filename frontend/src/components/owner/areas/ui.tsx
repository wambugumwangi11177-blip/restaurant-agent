"use client";
import { blockAnchor } from "@/lib/owner/features";
import { createContext, useContext, type ReactNode } from "react";
export const AreaFocus = createContext("");
import ChartEmpty, { isEmpty } from "@/components/charts/ChartEmpty";
import AssumptionChip from "@/components/owner/settings/AssumptionChip";
import StateChip from "@/components/owner/StateChip";
import type { Block } from "@/lib/owner/types";

/** One block of an area: its owner-word title, its state in words, and either its content or — when it has none — the reason. */
export function BlockFrame({ title, block, children, quiet = false }: {
  title: string;
  block: Block;
  /** A function, called only when the block has data: a block with nothing never evaluates the fields it does not have. */
  children: () => ReactNode;
  /** an information block has no data state worth a chip */
  quiet?: boolean;
}) {
  const focus = useContext(AreaFocus);
  if (focus && focus !== blockAnchor(title)) return null;
  const empty = isEmpty(block.state);
  return (
    <section id={blockAnchor(title)} aria-label={title} className="rounded-lg border border-[var(--v-border)] bg-[var(--v-bg)] p-3.5 sm:p-4">
      <div className="mb-2.5 flex flex-wrap items-center gap-2">
        <h4 className="text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--v-muted-foreground)]">{title}</h4>
        {!quiet && <StateChip block={block} />}
      </div>
      {empty ? <ChartEmpty state={block.state} reason={block.reason as string | null | undefined} day={block.day} of={block.of} height={64} /> : children()}
      <Rules block={block} />
    </section>
  );
}

export function Stat({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--v-muted-foreground)]">{label}</p>
      <p className="font-display mt-0.5 text-lg font-semibold tracking-[-0.02em]">{value}</p>
      {note && <p className="text-[11px] text-[var(--v-muted-foreground)]">{note}</p>}
    </div>
  );
}

export function Note({ children }: { children: ReactNode }) {
  return <p className="mt-2 text-[11px] leading-relaxed text-[var(--v-muted-foreground)]">{children}</p>;
}

export function Pill({ children, tone = "quiet" }: { children: ReactNode; tone?: "good" | "warn" | "bad" | "quiet" }) {
  const cls = { good: "bg-[hsl(150_28%_41%_/_0.12)] text-[var(--v-good)]", warn: "bg-[hsl(38_80%_44%_/_0.14)] text-[var(--v-warn)]", bad: "bg-[hsl(4_61%_52%_/_0.12)] text-[var(--v-destructive)]", quiet: "bg-[var(--v-muted)] text-[var(--v-muted-foreground)]" }[tone];
  return <span className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-bold ${cls}`}>{children}</span>;
}

export const Grid = ({ children, cols = 3 }: { children: ReactNode; cols?: 2 | 3 | 4 }) => (
  <div className={`grid grid-cols-2 gap-3 ${cols === 3 ? "sm:grid-cols-3" : cols === 4 ? "sm:grid-cols-4" : ""}`}>{children}</div>
);

export const Empty = ({ children }: { children: ReactNode }) => <p className="text-xs text-[var(--v-muted-foreground)]">{children}</p>;

/** The owner's own rules a block was judged by, each with a way to change it: "Based on: Wages target 32% · Change". */
function Rules({ block }: { block: Block }) {
  const list = block.assumptions?.length ? block.assumptions : block.assumption ? [block.assumption] : [];
  const seen = new Set<string>();
  const rules = list.filter((a) => (seen.has(a.setting) ? false : (seen.add(a.setting), true)));
  if (rules.length === 0 || isEmpty(block.state)) return null;
  return <div className="mt-3 flex flex-wrap gap-x-4 gap-y-0.5 border-t border-[var(--v-border)] pt-2">{rules.map((a) => <AssumptionChip key={a.setting} assumption={a} />)}</div>;
}
