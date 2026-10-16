import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import AnswerCard from "@/components/owner/ask/AnswerCard";
import { asOwnerAnswer, isGuidance, rowValue, type OwnerAnswer } from "@/lib/owner/ask";
import what from "./fixtures/owner/ask_what.json";
import why from "./fixtures/owner/ask_why.json";
import whatIf from "./fixtures/owner/ask_what_if.json";
import todo from "./fixtures/owner/ask_what_to_do.json";
import branches from "./fixtures/owner/ask_compare_branches.json";
import periods from "./fixtures/owner/ask_compare_periods.json";
import cash from "./fixtures/owner/ask_cash.json";
import unavailable from "./fixtures/owner/ask_unavailable.json";

afterEach(cleanup);
const as = (a: unknown) => a as OwnerAnswer;
const show = (a: unknown, onAsk = vi.fn()) => { render(<AnswerCard answer={as(a)} onAsk={onAsk} />); return onAsk; };

describe("one answer card for five forms", () => {
  it("every answer says its form and topic, its state in words, and its sentence", () => {
    for (const a of [what, why, whatIf, todo, branches, periods, cash, unavailable]) {
      show(a);
      expect(screen.getByText(as(a).headline)).toBeTruthy();
      expect(document.querySelector(`[data-form="${as(a).form}"]`)).toBeTruthy();
      expect(document.querySelector(`[data-form="${as(a).form}"]`)!.textContent).toContain(as(a).topic_label);
      cleanup();
    }
  });

  it("WHAT: the figures sit under the sentence in KES and percent, with their notes", () => {
    show(what);
    const sales = screen.getByText("Sales", { selector: "dt" }).closest("div")!;
    expect(within(sales).getByText("KES 212,280")).toBeTruthy();
    expect(screen.getByText("What you kept, out of every KES 100 sold").closest("div")!.textContent).toContain("11.4%");
    expect(screen.getByText("Ingredients", { selector: "dt" }).closest("div")!.textContent).toContain("-KES 62,120");
  });

  it("WHY: the day's sales beside a usual day, the drivers numbered in order, and what was checked folded away", () => {
    show(why);
    expect(screen.getByText("Sales on Tuesday 20 Oct")).toBeTruthy();
    const drivers = within(screen.getByRole("list", { name: "What the records show" })).getAllByRole("listitem");
    expect(drivers).toHaveLength(2);
    expect(drivers[0].textContent).toContain("Mashujaa Day");
    expect(drivers[1].textContent).toContain("Chips ran out");
    expect(drivers[1].textContent).toContain("ran short at");
    const fold = screen.getByText(/Also checked, nothing unusual \(2\)/).closest("details")!;
    expect(fold.textContent).toContain("Fewer staff");
    expect(fold.textContent).toContain("Cancelled sales");
  });

  it("WHAT IF: the verdict, both prices and what the answer rests on", () => {
    show(whatIf);
    expect(screen.getByText("Worth trying", { selector: "span" })).toBeTruthy();
    expect(screen.getByText("Chips now").closest("div")!.textContent).toContain("KES 300");
    expect(screen.getByText("Chips at").closest("div")!.textContent).toContain("KES 350");
    expect(screen.getByText("Profit a month").closest("div")!.textContent).toContain("KES 1,899");
    expect(screen.getByText("What this rests on")).toBeTruthy();
    expect(screen.getByText(/rough guide/)).toBeTruthy();
  });

  it("WHAT SHOULD I DO: ideas numbered biggest first, the ones that meet the goal marked, each with its Why", () => {
    show(todo);
    const ideas = within(screen.getByRole("list", { name: "Ideas, biggest first" })).getAllByRole("listitem");
    expect(ideas.length).toBe(as(todo).rows.length);
    expect(ideas[0].textContent).toContain("KES 7,406");
    expect(ideas[0].textContent).toContain("a month");
    expect(ideas[0].className).toContain("150_28%");                                           // inside the goal
    expect(ideas[1].className).not.toContain("150_28%");
    fireEvent.click(within(ideas[0]).getByText("Why?"));
    expect(within(ideas[0]).getByText(/the kitchen used/)).toBeTruthy();
  });

  it("COMPARE branches: a table with each branch's ingredients, wages and sales, and the gap beneath", () => {
    show(branches);
    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(within(table).getByRole("columnheader", { name: "Ingredients" })).toBeTruthy();
    expect(rows[1].textContent).toContain("Demo Restaurant");
    expect(rows.some((r) => r.textContent?.includes("Kasarani") && r.textContent.includes("37%"))).toBe(true);
    expect(screen.getByText("Difference").closest("div")!.textContent).toContain("7.8 points");
  });

  it("COMPARE periods: each side with its days, sales, orders and average order", () => {
    show(periods);
    const table = screen.getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Average order" })).toBeTruthy();
    const [, thisWeek, lastWeek] = within(table).getAllByRole("row");
    expect(thisWeek.textContent).toContain("This week so far");
    expect(thisWeek.textContent).toContain("KES 49,570");
    expect(lastWeek.textContent).toContain("Last week");
  });

  it("an answer with nothing to say shows its reason and the questions to try instead, no empty figures", () => {
    const onAsk = show(unavailable);
    expect(screen.getByText(/couldn't find a dish called "Unicorn steak"/)).toBeTruthy();
    expect(screen.queryByRole("list", { name: /Ideas/ })).toBeNull();
    expect(screen.queryByRole("definition")).toBeNull();
    fireEvent.click(screen.getAllByRole("button")[0]);
    expect(onAsk).toHaveBeenCalledWith(as(unavailable).next[0]);
  });

  it("no answer prints a dash where a figure should be, or a system word, or integer cents", () => {
    for (const a of [what, why, whatIf, todo, branches, periods, cash]) {
      show(a);
      const text = document.body.textContent ?? "";
      expect(text).not.toMatch(/\s—\s*(?:KES|$)/);
      expect(text).not.toMatch(/\bcents\b|undefined|NaN|null/);
      cleanup();
    }
  });
});

describe("what an owner's words are sent to", () => {
  it("a request for help or an explanation is guidance; a question about the owner's figures is not", () => {
    for (const q of ["Show me how this software can help my restaurant.", "Help me solve a problem.", "Can you help with a creative idea?", "I want to change something in my app.",
      "Any ideas for the weekend?", "Tips for cutting waste", "Brainstorm a promotion"]) expect(isGuidance(q), q).toBe(true);
    for (const q of ["Am I making a profit this month?", "What should I do to make more money?", "How can I find KES 20,000 more a month?", "Why was Tuesday bad?",
      "What if I raise the price of Chips to 350?", "Compare my branches", "Who should I win back?"]) expect(isGuidance(q), q).toBe(false);
  });

  it("a saved message is one of our answers only if it has a form, a sentence and rows", () => {
    expect(asOwnerAnswer(what)?.form).toBe("what");
    expect(asOwnerAnswer({ module: "ops", answer_text: "x" })).toBeNull();
    expect(asOwnerAnswer(null)).toBeNull();
    expect(asOwnerAnswer("text")).toBeNull();
  });

  it("figures are written the way the rest of the app writes them", () => {
    expect(rowValue({ value: 1899.39, unit: "kes" })).toBe("KES 1,899");
    expect(rowValue({ value: -8.2, unit: "pct" })).toBe("-8.2%");
    expect(rowValue({ value: 7.8, unit: "pct_points" })).toBe("7.8 points");
    expect(rowValue({ value: 5.6, unit: "hours" })).toBe("5.6 hours");
    expect(rowValue({ value: 3, unit: "count" })).toBe("3");
    expect(rowValue({ value: null, unit: "kes" })).toBe("");
    expect(rowValue({ value: 5, unit: "text" })).toBe("");
  });
});
