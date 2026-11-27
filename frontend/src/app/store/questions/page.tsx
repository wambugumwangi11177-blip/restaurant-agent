"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { loadSetup, stepById, type SetupPayload, type SetupQuestion, type GivenAnswer } from "@/lib/storeSetup";

type Seed = { name: string; brings: string; arrival: string };

function answerDisplay(answer: GivenAnswer): string {
  if (answer.delegated) {
    const who = answer.delegate_to === "accountant" ? "the accountant" : "the owner";
    return `${answer.label} (sent to ${who})`;
  }
  return answer.label;
}

export default function QuestionsPage() {
  const router = useRouter();
  const [setup, setSetup] = useState<SetupPayload | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [editingQuestionId, setEditingQuestionId] = useState<string | null>(null);

  useEffect(() => {
    loadSetup().then(setSetup).catch(() => setError("The questions could not be loaded."));
  }, []);

  const step = stepById(setup, "questionnaire");
  const answered = useMemo(() => new Set((setup?.answers ?? []).map((answer) => answer.question_id)), [setup]);
  const questions = step?.questions ?? [];
  const editingQuestion = editingQuestionId ? questions.find((q) => q.id === editingQuestionId) : undefined;
  const nextUnanswered = questions.find((question) => !answered.has(question.id));
  const activeQuestion = editingQuestion ?? nextUnanswered;
  const showSummary = setup && !activeQuestion;

  async function choose(question: SetupQuestion, value: string, suppliers?: Seed[]) {
    setSaving(true);
    setError("");
    try {
      const response = await api.post("/api/v1/staff-setup/questionnaire", {
        question_id: question.id,
        value,
        suppliers: suppliers ?? [],
      });
      const opens = response.data.opens as string | null;
      setEditingQuestionId(null);
      if (opens && opens !== "/store") {
        router.push(opens);
        return;
      }
      setSetup(await loadSetup());
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "That answer was not saved.");
    } finally {
      setSaving(false);
    }
  }

  if (setup && step?.state === "locked") {
    return (
      <section className="owner-glass-panel rounded-3xl p-4">
        <h2 className="font-semibold">Questions are locked</h2>
        <p className="mt-2 text-sm leading-6 text-zinc-300">{step.locked_reason}</p>
        <Link href="/store/account" className="mt-4 inline-flex min-h-11 items-center leviii-btn-primary px-4">
          Open account
        </Link>
      </section>
    );
  }

  if (showSummary) {
    const ordered = questions
      .map((q) => ({ q, answer: (setup?.answers ?? []).find((a) => a.question_id === q.id) }))
      .filter((row): row is { q: SetupQuestion; answer: GivenAnswer } => Boolean(row.answer));

    return (
      <section className="owner-glass-panel owner-form-clearance space-y-4 rounded-3xl p-4">
        <h2 className="font-semibold">Your answers</h2>
        <p className="text-sm text-zinc-400">You can change any answer. The owner sees these on Staff.</p>
        <ul className="space-y-4">
          {ordered.map(({ q, answer }) => (
            <li key={q.id} className="rounded-2xl border border-white/10 p-3">
              <p className="text-sm font-medium leading-6 text-zinc-100">{q.prompt}</p>
              <p className="mt-1 text-sm text-zinc-300">{answerDisplay(answer)}</p>
              <button
                type="button"
                className="mt-2 text-xs font-semibold text-[var(--accent)] underline-offset-2 hover:underline"
                onClick={() => setEditingQuestionId(q.id)}
              >
                Change
              </button>
            </li>
          ))}
        </ul>
        {error && <p className="text-sm text-red-300">{error}</p>}
      </section>
    );
  }

  if (!activeQuestion) {
    return (
      <section className="owner-glass-panel rounded-3xl p-4 text-sm text-zinc-400">
        {setup ? "Loading the next question…" : "Loading…"}
      </section>
    );
  }

  const progressIndex = questions.findIndex((q) => q.id === activeQuestion.id);

  return (
    <section className="owner-glass-panel owner-form-clearance space-y-3 rounded-3xl p-4">
      <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">
        {progressIndex + 1} of {questions.length}
      </p>
      <h2 className="text-lg font-semibold leading-7">{activeQuestion.prompt}</h2>
      {error && <p className="text-sm text-red-300">{error}</p>}
      {activeQuestion.kind === "suppliers" ? (
        <SupplierNames question={activeQuestion} saving={saving} onSubmit={choose} />
      ) : (
        <div className="space-y-2">
          {activeQuestion.answers.map((answer) => (
            <button
              key={answer.value}
              type="button"
              disabled={saving}
              onClick={() => choose(activeQuestion, answer.value)}
              className="min-h-11 w-full rounded-full border border-white/20 px-4 text-sm font-semibold disabled:opacity-50"
            >
              {answer.label || answer.value}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function SupplierNames({
  question,
  saving,
  onSubmit,
}: {
  question: SetupQuestion;
  saving: boolean;
  onSubmit: (question: SetupQuestion, value: string, suppliers?: Seed[]) => Promise<void>;
}) {
  const brings = question.brings?.length ? question.brings : ["Main food", "Alcohol", "Both", "Other"];
  const arrivals = question.arrivals?.length
    ? question.arrivals
    : [
        { value: "phone", label: "Phone order" },
        { value: "scheduled", label: "Scheduled delivery" },
        { value: "pickup", label: "Pickup" },
        { value: "other", label: "Other" },
      ];
  const [rows, setRows] = useState<Seed[]>([{ name: "", brings: brings[0], arrival: arrivals[0].value }]);
  const [localError, setLocalError] = useState("");

  function update(index: number, patch: Partial<Seed>) {
    setRows((current) => current.map((row, rowIndex) => (rowIndex === index ? { ...row, ...patch } : row)));
  }

  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault();
        const filled = rows.map((row) => ({ ...row, name: row.name.trim() })).filter((row) => row.name);
        if (filled.length === 0) {
          setLocalError("Name at least one supplier.");
          return;
        }
        setLocalError("");
        void onSubmit(question, "listed", filled);
      }}
    >
      {rows.map((row, index) => (
        <div key={index} className="space-y-2 rounded-2xl border border-white/10 p-3">
          <label className="block text-sm">
            Name
            <input
              value={row.name}
              onChange={(event) => update(index, { name: event.target.value })}
              className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3"
            />
          </label>
          <label className="block text-sm">
            What they bring
            <select
              value={row.brings}
              onChange={(event) => update(index, { brings: event.target.value })}
              className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/40 px-3"
            >
              {brings.map((option) => (
                <option key={option}>{option}</option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            How supplies arrive
            <select
              value={row.arrival}
              onChange={(event) => update(index, { arrival: event.target.value })}
              className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/40 px-3"
            >
              {arrivals.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      ))}
      <button
        type="button"
        className="min-h-11 w-full rounded-full border border-white/20 text-sm font-semibold"
        onClick={() => setRows((current) => [...current, { name: "", brings: brings[0], arrival: arrivals[0].value }])}
      >
        Add another supplier
      </button>
      {localError && <p className="text-sm text-red-300">{localError}</p>}
      <button type="submit" disabled={saving} className="min-h-11 w-full leviii-btn-primary disabled:opacity-50">
        Save suppliers
      </button>
      {question.answers.filter((answer) => answer.delegate).map((answer) => (
        <button
          key={answer.value}
          type="button"
          disabled={saving}
          onClick={() => onSubmit(question, answer.value)}
          className="min-h-11 w-full rounded-full border border-white/20 text-sm font-semibold disabled:opacity-50"
        >
          {answer.label || "I don't know"}
        </button>
      ))}
    </form>
  );
}