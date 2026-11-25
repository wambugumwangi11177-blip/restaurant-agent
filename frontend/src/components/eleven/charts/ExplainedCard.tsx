"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import ChartEmpty from "./ChartEmpty";

export type Tone = "good" | "watch" | "bad" | "neutral";

// Colour always comes with a word (Eleven guide, Rule 4).
const TONE: Record<Tone, { dot: string; word: string; text: string }> = {
  good: { dot: "bg-emerald-400", word: "Healthy", text: "text-emerald-300" },
  watch: { dot: "bg-amber-400", word: "Watch", text: "text-amber-300" },
  bad: { dot: "bg-red-400", word: "Check", text: "text-red-300" },
  neutral: { dot: "bg-zinc-400", word: "Note", text: "text-zinc-300" },
};

export type Verdict = { tone: Tone; text: string };

/**
 * One chart = one headline number, one plain verdict, the picture,
 * a "What this shows" line, and an optional "Why?" that shows how it was worked out.
 */
export default function ExplainedCard({
  title,
  headline,
  sub,
  verdict,
  what,
  why,
  freshness,
  detailHref,
  hasData,
  emptyHint,
  children,
}: {
  title: string;
  headline?: string;
  sub?: string;
  verdict?: Verdict;
  what: string;
  why?: string;
  freshness?: string;
  detailHref?: string;
  hasData: boolean;
  emptyHint: string;
  children: ReactNode;
}) {
  const tone = verdict ? TONE[verdict.tone] : null;
  return (
    <article className="owner-glass-panel space-y-3 p-4" data-testid="explained-card">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-xs font-medium uppercase tracking-wide text-zinc-400">{title}</h3>
        {detailHref && hasData ? (
          <Link href={detailHref} className="text-xs text-zinc-300 underline-offset-2 hover:underline">
            Details →
          </Link>
        ) : null}
      </div>

      {hasData && headline ? (
        <div>
          <p className="text-xl leading-tight text-zinc-50">{headline}</p>
          {sub ? <p className="mt-0.5 text-xs text-zinc-400">{sub}</p> : null}
        </div>
      ) : null}

      {hasData && verdict && tone ? (
        <p className={`flex items-center gap-2 text-sm ${tone.text}`}>
          <span className={`inline-block h-2 w-2 rounded-full ${tone.dot}`} aria-hidden />
          <span className="font-medium">{tone.word}:</span>
          <span className="text-zinc-200">{verdict.text}</span>
        </p>
      ) : null}

      <div className="min-h-[120px] w-full">{hasData ? children : <ChartEmpty hint={emptyHint} />}</div>

      <p className="text-xs leading-5 text-zinc-300">
        <span className="mr-1 font-semibold uppercase tracking-wide text-zinc-400">What this shows</span>
        {what}
      </p>

      {hasData && why ? (
        <details className="text-xs text-zinc-400">
          <summary className="cursor-pointer select-none text-zinc-300">Why?</summary>
          <p className="mt-1 leading-5">{why}</p>
        </details>
      ) : null}

      {hasData && freshness ? (
        <p className="text-[11px] uppercase tracking-wide text-zinc-500">{freshness}</p>
      ) : null}
    </article>
  );
}
