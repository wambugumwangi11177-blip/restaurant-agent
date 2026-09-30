"use client";
// "Ideas for you": the numbers are checked first (deterministic, instant), then the AI adds
// a few more ideas built on the same evidence. The owner never chooses between the two.
import { useState } from "react";
import Link from "next/link";
import { ChevronRight, Lightbulb, Sparkles } from "lucide-react";
import api from "@/lib/api";

type FromNumbers = { area: string; href: string; idea: string; why: string; next_step: string; expected: string | null };
type Result = { checked: number; from_numbers: FromNumbers[]; creative: string[] };

export default function DemoIdeas() {
  const [numbers, setNumbers] = useState<Result | null>(null);
  const [more, setMore] = useState<"idle" | "loading" | "ready" | "none">("idle");
  const [ideas, setIdeas] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  async function run() {
    if (busy) return;
    setBusy(true);
    setError(false);
    setMore("idle");
    setIdeas([]);
    try {
      const first = await api.post<Result>("/api/v1/demo/ideas", { creative: false });
      setNumbers(first.data);
    } catch {
      setError(true);
      setBusy(false);
      return;
    }
    setBusy(false);
    setMore("loading");
    try {
      const second = await api.post<Result>("/api/v1/demo/ideas", { creative: true }, { timeout: 90000 });
      setIdeas(second.data.creative ?? []);
      setMore(second.data.creative?.length ? "ready" : "none");
    } catch {
      setMore("none");
    }
  }

  return (
    <section aria-labelledby="ideas-box-heading" className="rounded-xl border border-[hsl(43_76%_57%_/_0.6)] bg-[hsl(42_71%_75%_/_0.16)] p-4 sm:p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--v-muted-foreground)]">Ideas for you</p>
          <h2 id="ideas-box-heading" className="font-display text-2xl font-semibold tracking-[-0.035em]">
            Fresh ideas to try this week
          </h2>
          <p className="mt-1.5 max-w-xl text-xs text-[var(--v-muted-foreground)]">
            We check your numbers first, then suggest ideas you can try. You decide what to use.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void run()}
          disabled={busy || more === "loading"}
          className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-[var(--v-primary)] px-4 py-2 text-xs font-bold text-[var(--v-primary-foreground)] hover:brightness-105 disabled:opacity-60"
        >
          <Sparkles size={14} />
          {busy ? "Checking your numbers…" : numbers ? "Get new ideas" : "Get ideas"}
        </button>
      </div>

      {error && (
        <p role="alert" className="mt-4 text-xs">
          We could not get ideas just now. Please try again.
        </p>
      )}

      {numbers && (
        <div className="mt-5 space-y-5">
          <div>
            <p className="text-xs font-semibold">From your numbers</p>
            <p className="text-[11px] text-[var(--v-muted-foreground)]">We looked at {numbers.checked} parts of your restaurant.</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {numbers.from_numbers.map((i) => (
                <article key={`${i.area}-${i.idea}`} className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-4">
                  <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">{i.area}</p>
                  <h3 className="mt-1.5 flex items-start gap-2 text-sm font-bold leading-snug">
                    <Lightbulb size={15} className="mt-0.5 shrink-0 text-[hsl(35_80%_42%)]" />
                    {i.idea}
                  </h3>
                  <p className="mt-2 text-xs leading-relaxed">{i.why}</p>
                  <p className="mt-1.5 text-xs leading-relaxed">
                    <b>Next step: </b>
                    {i.next_step}
                  </p>
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                    {i.expected && <span className="text-[11px] font-semibold text-[var(--v-primary)]">{i.expected}</span>}
                    <Link href={i.href} className="inline-flex items-center gap-0.5 text-[11px] font-semibold text-[var(--v-primary)]">
                      See the numbers <ChevronRight size={12} />
                    </Link>
                  </div>
                </article>
              ))}
            </div>
          </div>

          <div>
            <p className="text-xs font-semibold">More ideas to try</p>
            {more === "loading" && (
              <p role="status" className="mt-2 flex items-center gap-2 text-xs text-[var(--v-muted-foreground)]">
                <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--v-primary)]" />
                Thinking of more ideas for your menu…
              </p>
            )}
            {more === "ready" && (
              <>
                <ul className="mt-3 space-y-2">
                  {ideas.map((idea) => (
                    <li key={idea} className="flex items-start gap-2 rounded-lg border border-[var(--v-border)] bg-[var(--v-card)] p-3 text-sm leading-relaxed">
                      <Sparkles size={14} className="mt-1 shrink-0 text-[hsl(35_80%_42%)]" />
                      {idea}
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-[11px] text-[var(--v-muted-foreground)]">Written by AI from your menu and numbers. These are ideas to test, not facts.</p>
              </>
            )}
            {more === "none" && (
              <p className="mt-2 text-xs text-[var(--v-muted-foreground)]">
                More ideas are not available right now. The ideas above still come straight from your numbers.{" "}
                <button type="button" onClick={() => void run()} className="font-semibold text-[var(--v-primary)] underline">
                  Try again
                </button>
              </p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
