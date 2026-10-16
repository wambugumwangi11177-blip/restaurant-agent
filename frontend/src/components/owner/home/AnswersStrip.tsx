"use client";
import { ChevronRight } from "lucide-react";
import { kes, plural, shortDay } from "@/lib/owner/format";
import type { OwnerHome } from "@/lib/owner/types";

type Tone = "good" | "bad" | "quiet";
type Answer = { id: "cash" | "leak" | "bill"; question: string; answer: string; tone: Tone; href: string };

const DOT: Record<Tone, string> = { good: "bg-[var(--v-good)]", bad: "bg-[var(--v-destructive)]", quiet: "bg-[var(--v-border)]" };

/** The three things an owner opens the app to find out, said in one line each: did the cash balance, what is costing me most, what is the next bill. */
export function answersFor(home: OwnerHome): Answer[] {
  const cash = home.pulse.money_match.cash;
  const checked = Number(cash.checked ?? 0);
  const look = Number(cash.to_check ?? 0);
  const cashAnswer: Answer =
    cash.state === "no_data" || cash.state === "unavailable"
      ? { id: "cash", question: "Did the cash balance?", answer: String(cash.reason ?? "No cash counts yet."), tone: "quiet", href: "#area-cash" }
      : look > 0
        ? { id: "cash", question: "Did the cash balance?", answer: `${plural(look, "count")} to look at, of ${checked} checked`, tone: "bad", href: "#area-cash" }
        : { id: "cash", question: "Did the cash balance?", answer: `Yes — all ${checked} counts match`, tone: "good", href: "#area-cash" };

  const top = home.costing_you_money.cards[0];
  const leakAnswer: Answer = top
    ? { id: "leak", question: top.tier === "now" ? "Happening now" : "What's costing me most?", answer: top.kes_month != null ? `${top.sentence} — about ${kes(top.kes_month)} a month` : top.sentence, tone: "bad", href: "#costing-you-money" }
    : { id: "leak", question: "What's costing me most?", answer: String(home.costing_you_money.reason ?? "Nothing we can see right now."), tone: "good", href: "#costing-you-money" };

  const bill = home.coming_up.bills.items?.[0];
  const billAnswer: Answer = bill
    ? { id: "bill", question: "What's the next bill?", answer: `${bill.name} — ${kes(bill.amount_kes)} ${bill.days_away === 0 ? "today" : `in ${plural(bill.days_away, "day")}`} (${shortDay(bill.due_on)})${bill.short ? " — your sales will not cover it" : ""}`, tone: bill.short ? "bad" : "quiet", href: "#coming-up" }
    : { id: "bill", question: "What's the next bill?", answer: String(home.coming_up.bills.reason ?? "No bills due soon."), tone: "quiet", href: "#coming-up" };
  return [cashAnswer, leakAnswer, billAnswer];
}

/**
 * Right under the greeting, so the answers are on the first screen of a phone and the detail is one tap away. Plain anchors on purpose:
 * a browser anchor fires `hashchange`, which is what opens the panel it points at (a client-side <Link> to a #hash does not).
 */
export default function AnswersStrip({ home }: { home: OwnerHome }) {
  return (
    <section aria-label="The answers you came for">
      <ul className="divide-y divide-[var(--v-border)] rounded-xl border border-[var(--v-border)] bg-[var(--v-card)]">
        {answersFor(home).map((a) => (
          <li key={a.id}>
            <a href={a.href} data-answer={a.id} className="flex min-h-14 items-center gap-3 px-4 py-2.5">
              <span aria-hidden className={`h-2.5 w-2.5 shrink-0 rounded-full ${DOT[a.tone]}`} />
              <span className="min-w-0 flex-1">
                <span className="block text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--v-muted-foreground)]">{a.question}</span>
                <span className="block text-[13px] font-semibold leading-snug">{a.answer}</span>
              </span>
              <ChevronRight size={16} aria-hidden className="shrink-0 text-[var(--v-muted-foreground)]" />
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
