import { stateWords, type Tone } from "@/lib/owner/format";
import type { Block } from "@/lib/owner/types";

const TONE: Record<Tone, string> = {
  good: "border-[hsl(150_28%_41%_/_0.35)] bg-[hsl(150_28%_41%_/_0.1)] text-[var(--v-good)]",
  info: "border-[hsl(201_47%_29%_/_0.3)] bg-[hsl(201_47%_29%_/_0.07)] text-[var(--v-primary)]",
  warn: "border-[hsl(38_80%_44%_/_0.4)] bg-[hsl(38_80%_44%_/_0.1)] text-[var(--v-warn)]",
  bad: "border-[hsl(4_61%_52%_/_0.4)] bg-[hsl(4_61%_52%_/_0.08)] text-[var(--v-destructive)]",
  quiet: "border-[var(--v-border)] bg-[var(--v-muted)] text-[var(--v-muted-foreground)]",
};

/** "Live" · "As entered up to 14 Oct" · "Learning · day 9 of 30" · "Out of date · 4 days old" · "Not available": a number's state, in words. */
export default function StateChip({ block, className = "" }: { block: Pick<Block, "state"> & Partial<Block>; className?: string }) {
  const { word, tone, detail } = stateWords(block);
  return (
    <span data-state={block.state} title={detail}
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold leading-4 ${TONE[tone]} ${className}`}>
      {word}
    </span>
  );
}
