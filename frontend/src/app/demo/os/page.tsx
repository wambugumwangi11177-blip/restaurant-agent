"use client";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import api from "@/lib/api";
import { VIBANDA_AREA_SECTIONS } from "@/lib/vibandaAreas";
type Answer = {
  answer_text: string;
  href: string;
  creative: boolean;
  cached: boolean;
  reason: string | null;
};
const STARTERS = [
  "Where can I save money?",
  "What is the sales forecast?",
  "What stock will run out?",
  "How can I improve menu margins?",
];
export default function DemoOS() {
  return (
    <Suspense fallback={<p>Loading OS…</p>}>
      <Workspace />
    </Suspense>
  );
}
function Workspace() {
  const params = useSearchParams();
  const [question, setQuestion] = useState(params.get("q") ?? "");
  const [topic, setTopic] = useState(params.get("topic") ?? "");
  const [creative, setCreative] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(false);
  const [turns, setTurns] = useState<{ question: string; answer: Answer }[]>(
    [],
  );
  async function send(q: string) {
    if (busy || q.trim().length < 3) return;
    setBusy(true);
    setError(false);
    try {
      const r = await api.post<Answer>(
        "/api/v1/demo/chat",
        { question: q.trim(), topic: topic || null, creative },
        { timeout: 45000 },
      );
      setTurns((t) => [...t.slice(-19), { question: q, answer: r.data }]);
      setQuestion("");
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="mx-auto max-w-4xl space-y-6 animate-rise-in">
      <div>
        <p className="text-xs uppercase tracking-widest text-[var(--v-muted-foreground)]">
          Your restaurant thinking partner
        </p>
        <h1 className="font-display mt-2 text-5xl">OS.</h1>
        <p className="mt-3 text-sm">
          Understand the evidence, explore possibilities, and decide what to do
          next.
        </p>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {STARTERS.map((q) => (
          <button
            disabled={busy}
            key={q}
            onClick={() => {
              setQuestion(q);
            }}
            className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-4 text-left text-sm hover:border-[var(--v-primary)]"
          >
            {q} →
          </button>
        ))}
      </div>
      <div className="space-y-4" aria-live="polite">
        {turns.map((t, i) => (
          <article
            key={i}
            className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5"
          >
            <h2 className="font-semibold">{t.question}</h2>
            <p className="mt-4 text-[10px] uppercase tracking-widest text-[var(--v-muted-foreground)]">
              {t.answer.creative
                ? "AI-written · grounded in sample evidence"
                : "Calculated scenario explanation"}
              {t.answer.cached ? " · cached" : ""}
            </p>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-7">
              {t.answer.answer_text}
            </p>
            {t.answer.reason && (
              <p className="mt-3 text-xs text-[var(--v-muted-foreground)]">
                {t.answer.reason}
              </p>
            )}
            <Link
              href={t.answer.href}
              className="mt-4 inline-block text-sm font-semibold text-[var(--v-primary)]"
            >
              Open supporting evidence →
            </Link>
          </article>
        ))}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send(question);
        }}
        className="space-y-4 rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5"
      >
        <label className="block text-sm">
          Focus area
          <select
            className="ml-3 rounded border border-[var(--v-border)] bg-[var(--v-card)] p-2"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
          >
            <option value="">Choose from my question</option>
            {VIBANDA_AREA_SECTIONS.flatMap((s) => s.areas).map(
              ([label, , slug]) => (
                <option key={slug} value={slug}>
                  {label}
                </option>
              ),
            )}
          </select>
        </label>
        <label className="block text-sm" htmlFor="demo-question">
          Ask your OS
        </label>
        <textarea
          id="demo-question"
          maxLength={500}
          minLength={3}
          required
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="What should I focus on today, and why?"
          rows={3}
          className="w-full rounded-lg border border-[var(--v-border)] bg-transparent p-3 text-sm"
        />
        <div className="flex flex-wrap items-center justify-between gap-4">
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={creative}
              onChange={(e) => setCreative(e.target.checked)}
            />{" "}
            Creative adviser · optional AI, cached to save tokens
          </label>
          <button
            disabled={busy || question.trim().length < 3}
            className="rounded-lg bg-[var(--v-primary)] px-5 py-3 text-sm text-[var(--v-primary-foreground)]"
          >
            {busy ? "Thinking…" : "Ask OS"}
          </button>
        </div>
        {error && (
          <p role="alert">
            Could not get an answer. Your question is preserved; try again.
          </p>
        )}
      </form>
      <p className="text-xs text-[var(--v-muted-foreground)]">
        Conversation stays in this page session. Ideas are proposals; this demo
        never executes business changes.
      </p>
    </div>
  );
}
