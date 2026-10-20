import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import AnswersStrip, { answersFor } from "@/components/owner/home/AnswersStrip";
import type { OwnerHome } from "@/lib/owner/types";
import demo from "./fixtures/owner/home.json";
import fresh from "./fixtures/owner/home_fresh.json";

afterEach(cleanup);

const home = () => structuredClone(demo) as unknown as OwnerHome;
const empty = () => structuredClone(fresh) as unknown as OwnerHome;
const row = (id: string) => document.querySelector(`[data-answer=${id}]`) as HTMLAnchorElement;

it("answers the three questions an owner opens the app for, each linking to its detail", () => {
  render(<AnswersStrip home={home()} />);
  expect(row("cash").textContent).toBe("Did the cash balance?2 counts to look at, of 27 checked");
  expect(row("leak").textContent).toMatch(/^What's costing me most\?Check where the Beef went: 2\.5 kg more was used than your sales explain — about KES 8,661 a month$/);
  expect(row("bill").textContent).toBe("What's the next bill?Rent — KES 70,000 in 3 days (18 Oct) — your sales will not cover it");
  expect([row("cash"), row("leak"), row("bill")].map((a) => a.getAttribute("href"))).toEqual(["#area-cash", "#costing-you-money", "#coming-up"]);
  expect(within(screen.getByRole("region", { name: "The answers you came for" })).getAllByRole("link")).toHaveLength(3);
});

it("says plainly when the cash balanced, and uses the singular for one count", () => {
  const h = home();
  h.pulse.money_match.cash.to_check = 0;
  expect(answersFor(h)[0]).toMatchObject({ answer: "Yes — all 27 counts match", tone: "good" });
  h.pulse.money_match.cash.to_check = 1;
  expect(answersFor(h)[0].answer).toBe("1 count to look at, of 27 checked");
});

it("what is happening now is asked as that, and a leak with no figure says so rather than guessing one", () => {
  const h = home();
  h.costing_you_money.cards[0] = { ...h.costing_you_money.cards[0], tier: "now", kes_month: null, sentence: "Beef is running low (1.0 left)" };
  expect(answersFor(h)[1]).toMatchObject({ question: "Happening now", answer: "Beef is running low (1.0 left)" });
});

it("a bill the sales will cover is not marked short, and one due today says today", () => {
  const h = home();
  h.coming_up.bills.items = [{ name: "Water", due_on: "2026-10-15", days_away: 0, amount_kes: 3200, short: false }];
  expect(answersFor(h)[2]).toMatchObject({ answer: "Water — KES 3,200 today (15 Oct)", tone: "quiet" });
});

it("a restaurant with nothing recorded gets each question's honest answer, not a blank or a dash", () => {
  render(<AnswersStrip home={empty()} />);
  expect(row("cash").textContent).toContain("No cash counts entered yet.");
  expect(row("leak").textContent).toMatch(/Nothing/);
  expect(row("bill").textContent).toContain("No bills entered yet.");
  expect([...document.querySelectorAll("a *")].filter((e) => e.children.length === 0 && e.textContent?.trim() === "—")).toEqual([]);
});

it("every row is a comfortable tap target", () => {
  render(<AnswersStrip home={home()} />);
  for (const a of document.querySelectorAll("a")) expect(a.className).toContain("min-h-14");
});
