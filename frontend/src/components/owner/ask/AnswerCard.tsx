"use client";
/**
 * One Ask LEVIII answer, in whichever of the five forms it came in (docs/v2/SPEC.md §4 P5.1). The sentence on top is written by code from
 * the figures below it; under it the figures themselves, what the answer rests on, and the questions that naturally come next.
 */
import type { ReactNode } from "react";
import InsightNote from "@/components/owner/InsightNote";
import StateChip from "@/components/owner/StateChip";
import { Assumptions, LABEL, Rows } from "@/components/owner/AnswerParts";
import { kes, pct } from "@/lib/owner/format";
import { rowValue, type AskForm, type Column, type Driver, type OwnerAnswer } from "@/lib/owner/ask";

type Ask = (question: string, form?: AskForm) => void;

const FORM_WORDS: Record<AskForm, string> = { what: "What", why: "Why", what_if: "What if", what_to_do: "What should I do", compare: "Compare" };

const label = LABEL;

// ── why ──────────────────────────────────────────────────────────────────────

function WhyBody({ answer }: { answer: OwnerAnswer }) {
  const drivers = answer.drivers ?? [];
  const found = drivers.filter((d) => d.found);
  const checked = drivers.filter((d) => !d.found);
  const facts = answer.rows.filter((r) => ["sales", "usual"].includes(r.key));
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        {facts.map((r) => (
          <div key={r.key}><p className={label}>{r.label}</p><p className="font-display text-lg font-semibold">{rowValue(r)}</p>{r.note && <p className="text-[11px] text-[var(--v-muted-foreground)]">{r.note}</p>}</div>
        ))}
      </div>
      {found.length > 0 && (
        <ol aria-label="What the records show" className="space-y-2">
          {found.map((d: Driver, i) => (
            <li key={d.key} className="rounded-lg border border-[hsl(38_80%_44%_/_0.4)] bg-[hsl(38_80%_44%_/_0.07)] p-3">
              <p className="text-xs font-bold"><span className="mr-2 text-[var(--v-muted-foreground)]">{i + 1}</span>{d.label}{d.value != null && d.unit !== "text" && <span className="ml-2 font-display">{rowValue(d)}</span>}</p>
              <p className="mt-1 text-[11px] leading-relaxed text-[var(--v-muted-foreground)]">{d.note}</p>
            </li>
          ))}
        </ol>
      )}
      {checked.length > 0 && (
        <details className="text-[11px] text-[var(--v-muted-foreground)]">
          <summary className="min-h-10 cursor-pointer py-2 font-semibold">Also checked, nothing unusual ({checked.length})</summary>
          <ul className="space-y-1 pb-1">{checked.map((d) => <li key={d.key}><b>{d.label}:</b> {d.note}</li>)}</ul>
        </details>
      )}
    </div>
  );
}

// ── compare ──────────────────────────────────────────────────────────────────

function CompareBody({ answer }: { answer: OwnerAnswer }) {
  const cols = answer.columns ?? [];
  const branches = answer.kind === "branches";
  const heads = branches ? ["", "Ingredients", "Wages", "Sales, 30 days"] : ["", "Sales", "Orders", "Average order", "Ingredients"];
  const cell = (c: Column): ReactNode[] => branches
    ? [pct(c.food_cost_pct), c.wages_pct == null ? "—" : pct(c.wages_pct), kes(c.sales)]
    : [kes(c.sales), String(c.orders), c.average_order == null ? "—" : kes(c.average_order), c.food_cost_pct == null ? "—" : pct(c.food_cost_pct)];
  return (
    <div className="space-y-3">
      {cols.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-[var(--v-border)]">
          <table className="w-full min-w-[20rem] text-left text-xs">
            <thead><tr className="bg-[var(--v-muted)]">{heads.map((h, i) => <th key={i} scope="col" className={`px-3 py-2 ${label}`}>{h}</th>)}</tr></thead>
            <tbody>{cols.map((c) => (
              <tr key={c.name ?? c.key} className="border-t border-[var(--v-border)]">
                <th scope="row" className="px-3 py-2 font-semibold">{c.name ?? c.label}{!branches && c.from && <span className="block text-[10px] font-normal text-[var(--v-muted-foreground)]">{c.days} days from {c.from}</span>}</th>
                {cell(c).map((v, i) => <td key={i} className="px-3 py-2">{v}</td>)}
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {branches && <Rows rows={answer.rows.filter((r) => r.key !== "food_cost_pct")} />}
    </div>
  );
}

// ── what should I do ─────────────────────────────────────────────────────────

function TodoBody({ answer }: { answer: OwnerAnswer }) {
  const reached = answer.covered_by;
  return (
    <ol aria-label="Ideas, biggest first" className="space-y-2">
      {answer.rows.map((r, i) => (
        <li key={r.id ?? i} className={`rounded-lg border p-3 ${reached && i < reached ? "border-[hsl(150_28%_41%_/_0.4)] bg-[hsl(150_28%_41%_/_0.06)]" : "border-[var(--v-border)] bg-[var(--v-bg)]"}`}>
          <div className="flex items-start justify-between gap-3">
            <p className="text-xs font-semibold leading-snug"><span className="mr-2 text-[var(--v-muted-foreground)]">{i + 1}</span>{r.label}</p>
            {r.value != null && r.unit === "kes" && <p className="font-display shrink-0 text-sm font-semibold">{kes(r.value)}<span className="block text-right text-[10px] font-normal text-[var(--v-muted-foreground)]">a month</span></p>}
          </div>
          {r.action && r.action !== r.label && <p className="mt-1 text-[11px] text-[var(--v-muted-foreground)]">{r.action}</p>}
          {r.why && <details className="mt-1 text-[11px] text-[var(--v-muted-foreground)]"><summary className="min-h-10 cursor-pointer py-2 font-semibold">Why?</summary><p className="pb-1">{r.why}</p></details>}
        </li>
      ))}
    </ol>
  );
}

// ── the card ─────────────────────────────────────────────────────────────────

export default function AnswerCard({ answer, onAsk }: { answer: OwnerAnswer; onAsk: Ask }) {
  const empty = answer.state === "no_data" || answer.state === "unavailable";
  const body = empty ? null
    : answer.form === "why" ? <WhyBody answer={answer} />
    : answer.form === "compare" ? <CompareBody answer={answer} />
    : answer.form === "what_to_do" ? <TodoBody answer={answer} />
    : <Rows rows={answer.rows} />;
  return (
    <div className="space-y-3" data-form={answer.form}>
      <div className="flex flex-wrap items-center gap-2">
        <span className={label}>{FORM_WORDS[answer.form]} · {answer.topic_label}</span>
        <StateChip block={{ state: answer.state, as_of: answer.as_of }} />
        {answer.form === "what_if" && answer.verdict && !empty && <span className="rounded-full bg-[var(--v-muted)] px-2 py-0.5 text-[10px] font-bold">{answer.verdict}</span>}
      </div>
      <p className="text-sm leading-relaxed">{answer.headline}</p>
      {body}
      <InsightNote insight={answer.insight} />
      <Assumptions items={answer.assumptions} />
      {answer.next.length > 0 && (
        <div className="flex flex-wrap gap-2" aria-label="Ask next">
          {answer.next.map((q) => <button key={q} type="button" onClick={() => onAsk(q)} className="min-h-10 rounded-full border border-[var(--v-border)] px-3 py-1.5 text-[11px] hover:border-[var(--v-primary)]">{q}</button>)}
        </div>
      )}
    </div>
  );
}
