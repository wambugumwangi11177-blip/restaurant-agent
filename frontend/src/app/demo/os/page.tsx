"use client";
// Demo Restaurant OS: chat-first, with prompted questions grouped by part of the restaurant.
// The owner never picks between "calculated" and "creative": every question gets the answer
// worked out from the numbers straight away, and an AI idea is added underneath when ready.
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { ChevronDown, Database, Lightbulb, Search, Send, Sparkles } from "lucide-react";
import api from "@/lib/api";
import { DEMO_QUESTION_SECTIONS, DEMO_STARTERS } from "@/lib/demoQuestions";

type Answer = {
  answer_text: string;
  module: string;
  title: string;
  href: string;
  creative: boolean;
  cached: boolean;
  reason: string | null;
  follow_ups?: string[];
};
type Turn = {
  id: string;
  question: string;
  topic?: string;
  answer?: Answer;
  idea: "idle" | "loading" | "ready" | "none";
  ideaText?: string;
  error?: boolean;
};

export default function DemoOS() {
  return (
    <Suspense fallback={<p role="status">Loading OS…</p>}>
      <Workspace />
    </Suspense>
  );
}

function Workspace() {
  const params = useSearchParams();
  const [input, setInput] = useState("");
  const [search, setSearch] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const asked = useRef(false);
  const endRef = useRef<HTMLDivElement>(null);

  const patch = (id: string, change: Partial<Turn>) =>
    setTurns((all) => all.map((t) => (t.id === id ? { ...t, ...change } : t)));

  async function send(question: string, topic?: string, retryId?: string) {
    const text = question.trim();
    if (text.length < 3 || text.length > 500 || busyRef.current) return;
    const id = retryId ?? crypto.randomUUID();
    if (retryId) patch(id, { error: false, answer: undefined, idea: "idle" });
    else setTurns((all) => [...all.slice(-19), { id, question: text, topic, idea: "idle" }]);
    busyRef.current = true;
    setBusy(true);
    try {
      const r = await api.post<Answer>("/api/v1/demo/chat", { question: text, topic: topic ?? null, creative: false }, { timeout: 30000 });
      patch(id, { answer: r.data, idea: "loading" });
      setInput("");
      // The AI idea arrives on its own; the owner can keep asking in the meantime.
      void api
        .post<Answer>("/api/v1/demo/chat", { question: text, topic: r.data.module, creative: true }, { timeout: 90000 })
        .then((res) => patch(id, res.data.creative ? { idea: "ready", ideaText: res.data.answer_text } : { idea: "none" }))
        .catch(() => patch(id, { idea: "none" }));
    } catch {
      patch(id, { error: true, idea: "none" });
      setInput(text);
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  // Questions can arrive from Home or an area page (?q=...&topic=...).
  const firstQuestion = params.get("q");
  const firstTopic = params.get("topic") || undefined;
  useEffect(() => {
    if (!firstQuestion || asked.current) return;
    asked.current = true;
    const timer = window.setTimeout(() => void send(firstQuestion, firstTopic), 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstQuestion, firstTopic]);

  useEffect(() => {
    if (turns.length) endRef.current?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
  }, [turns.length]);

  const needle = search.trim().toLowerCase();
  const sections = DEMO_QUESTION_SECTIONS.map((section) => ({
    ...section,
    areas: section.areas
      .map((area) => ({
        ...area,
        questions: area.questions.filter((q) => !needle || area.label.toLowerCase().includes(needle) || q.toLowerCase().includes(needle)),
      }))
      .filter((area) => area.questions.length > 0),
  })).filter((section) => section.areas.length > 0);

  return (
    <div className="mx-auto max-w-4xl animate-rise-in space-y-6 pb-8">
      <header className="space-y-3">
        <div className="inline-flex items-center gap-2 rounded-full border border-[var(--v-border)] bg-[hsl(42_40%_99%_/_0.65)] px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">
          <Sparkles size={13} className="text-[var(--v-primary)]" /> Your restaurant partner
        </div>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="font-display text-[clamp(2rem,4vw,3.25rem)] font-semibold leading-tight tracking-[-0.045em]">
              What would you like to know<span className="text-[var(--v-primary)]">?</span>
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-[var(--v-muted-foreground)]">
              Ask in your own words, or pick a question below. Answers come straight from your numbers.
            </p>
          </div>
          {turns.length > 0 && (
            <button type="button" onClick={() => setTurns([])} className="rounded-lg border border-[var(--v-border)] px-3 py-2 text-xs font-semibold hover:bg-[var(--v-card)]">
              New conversation
            </button>
          )}
        </div>
      </header>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send(input);
        }}
        className="sticky bottom-20 z-20 flex items-end gap-2 rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-2 shadow-[0_12px_40px_hsl(201_47%_29%_/.10)] focus-within:border-[hsl(201_47%_29%_/.65)] md:bottom-3"
      >
        <textarea
          value={input}
          maxLength={500}
          rows={1}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send(input);
            }
          }}
          aria-label="Ask a question about your restaurant"
          placeholder="Ask a question, for example: what should I do about my stock?"
          className="max-h-32 min-h-11 min-w-0 flex-1 resize-y bg-transparent px-3 py-3 text-sm leading-relaxed outline-none placeholder:text-[hsl(207_12%_46%_/.75)]"
        />
        <button
          type="submit"
          disabled={busy || input.trim().length < 3}
          aria-label="Ask OS"
          className="mb-0.5 flex h-10 shrink-0 items-center justify-center gap-2 rounded-lg bg-[var(--v-primary)] px-4 text-xs font-bold text-[var(--v-primary-foreground)] disabled:opacity-50"
        >
          <Send size={15} /> {busy ? "Thinking…" : "Ask OS"}
        </button>
      </form>

      {turns.length === 0 && (
        <>
          <p className="flex items-start gap-2 rounded-lg bg-[hsl(42_40%_99%_/_0.58)] px-3 py-2.5 text-xs text-[var(--v-muted-foreground)]">
            <Database size={14} className="mt-0.5 shrink-0 text-[var(--v-primary)]" />
            This is a sample restaurant, so you can try every question safely. Nothing you ask changes any records.
          </p>
          <section aria-label="Start with a question" className="grid gap-2 sm:grid-cols-2">
            {DEMO_STARTERS.map((s) => (
              <button
                type="button"
                key={s.text}
                disabled={busy}
                onClick={() => void send(s.text, s.topic)}
                className="group flex min-h-16 items-center justify-between gap-3 rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-4 text-left text-sm font-medium transition hover:-translate-y-0.5 hover:border-[var(--v-primary)]/50 hover:shadow-sm"
              >
                <span>{s.text}</span>
                <span className="text-lg text-[var(--v-primary)] transition-transform group-hover:translate-x-1">→</span>
              </button>
            ))}
          </section>
        </>
      )}

      {turns.length > 0 && (
        <div className="space-y-5" aria-live="polite">
          {turns.map((t) => (
            <article key={t.id} className="space-y-3">
              <div className="ml-auto max-w-[92%] sm:max-w-[78%]">
                <p className="mb-1 text-right text-[10px] font-semibold text-[var(--v-muted-foreground)]">Your question</p>
                <div className="rounded-2xl rounded-br-sm bg-[var(--v-primary)] px-4 py-3 text-sm leading-relaxed text-[var(--v-primary-foreground)]">{t.question}</div>
              </div>
              <div className="max-w-[96%] rounded-2xl rounded-bl-sm border border-[var(--v-border)] bg-[var(--v-card)] p-4 shadow-sm sm:max-w-[88%]">
                {t.error ? (
                  <div role="alert" className="space-y-2">
                    <p className="text-sm">I could not get an answer just now. Your question is still here so you can try again.</p>
                    <button type="button" onClick={() => void send(t.question, t.topic, t.id)} className="rounded-lg border border-[var(--v-border)] px-3 py-1.5 text-xs font-semibold">
                      Try again
                    </button>
                  </div>
                ) : t.answer ? (
                  <div className="space-y-3">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--v-muted-foreground)]">From your numbers · {t.answer.title}</p>
                    {t.answer.answer_text.split("\n\n").map((para) => (
                      <p key={para} className="text-sm leading-relaxed">
                        {para}
                      </p>
                    ))}
                    <Link href={t.answer.href} className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--v-primary)]">
                      See the numbers: {t.answer.title} →
                    </Link>
                    {t.idea === "loading" && (
                      <p role="status" className="flex items-center gap-2 border-t border-[var(--v-border)] pt-3 text-xs text-[var(--v-muted-foreground)]">
                        <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--v-primary)]" />
                        Thinking of an idea to go with this…
                      </p>
                    )}
                    {t.idea === "ready" && t.ideaText && (
                      <div className="rounded-xl border border-[hsl(43_76%_57%_/_0.6)] bg-[hsl(42_71%_75%_/_0.18)] p-3">
                        <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--v-muted-foreground)]">
                          <Lightbulb size={12} className="text-[hsl(35_80%_42%)]" /> An idea to try
                        </p>
                        <p className="mt-1.5 text-sm leading-relaxed">{t.ideaText}</p>
                        <p className="mt-1.5 text-[10px] text-[var(--v-muted-foreground)]">Written by AI from your numbers. An idea to test, not a fact.</p>
                      </div>
                    )}
                    {t.answer.follow_ups?.length ? (
                      <div className="flex flex-wrap gap-2 pt-1">
                        {t.answer.follow_ups.map((f) => (
                          <button key={f} type="button" disabled={busy} onClick={() => void send(f, t.answer?.module)} className="rounded-full border border-[var(--v-border)] px-3 py-1.5 text-[11px] hover:border-[var(--v-primary)]">
                            {f}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <p role="status" className="flex items-center gap-2 text-sm text-[var(--v-muted-foreground)]">
                    <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--v-primary)]" />
                    Working on your question…
                  </p>
                )}
              </div>
            </article>
          ))}
          <div ref={endRef} aria-hidden="true" />
        </div>
      )}

      <section className="space-y-3" aria-label="Explore by part of the restaurant">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--v-muted-foreground)]">Explore by part of the restaurant</p>
            <h2 className="font-display mt-1 text-xl font-semibold">Find a useful place to start</h2>
          </div>
          <label className="flex items-center gap-2 rounded-lg border border-[var(--v-border)] bg-[var(--v-card)] px-3 py-2">
            <Search size={14} className="text-[var(--v-muted-foreground)]" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search questions" placeholder="Search questions" className="w-44 bg-transparent text-xs outline-none" />
          </label>
        </div>
        {sections.map((section) => (
          <details key={section.id} open={turns.length === 0 && section.id === "health" ? true : !!needle} className="group rounded-xl border border-[var(--v-border)] bg-[var(--v-card)]">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 p-4">
              <span>
                <span className="block text-sm font-semibold">{section.title}</span>
                <span className="mt-1 block text-xs text-[var(--v-muted-foreground)]">{section.areas.length} parts to explore</span>
              </span>
              <ChevronDown size={16} className="shrink-0 text-[var(--v-muted-foreground)] transition-transform group-open:rotate-180" />
            </summary>
            <div className="space-y-3 border-t border-[var(--v-border)] px-3 py-3 sm:px-4">
              {section.areas.map((area) => (
                <div key={area.slug} className="rounded-lg bg-[hsl(42_40%_99%_/_0.56)] p-3">
                  <h3 className="text-sm font-semibold">{area.label}</h3>
                  <p className="mt-0.5 text-xs text-[var(--v-muted-foreground)]">{area.note}</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {area.questions.map((q) => (
                      <button
                        type="button"
                        key={`${area.slug}-${q}`}
                        disabled={busy}
                        onClick={() => void send(q, area.slug)}
                        className="rounded-lg border border-[var(--v-border)] bg-white/70 px-3 py-2 text-left text-xs transition hover:border-[var(--v-primary)]/50"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </details>
        ))}
        {sections.length === 0 && <p className="text-xs text-[var(--v-muted-foreground)]">No questions match. Try a different word, or type your own question above.</p>}
      </section>
    </div>
  );
}
