import { expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import GuideFigures from "../src/components/owner/explain/GuideFigures";

const empty = {
  three_way: { state: "no_data", reason: "No count yet.", legs: [] },
  short_count: { state: "no_data", reason: "No count yet.", bars: [] },
  stock_history: { state: "no_data", reason: "No stock yet.", points: [] },
  shilling: { state: "no_data", reason: "No order yet.", steps: [] },
  price_tree: { state: "no_data", reason: "No dish yet.", nodes: [] },
  elasticity: { state: "no_data", reason: "No price change yet.", points: [] },
  price_ladder: { state: "no_data", reason: "No prices yet.", rungs: [] },
  pareto: { state: "no_data", reason: "No sales yet.", points: [] },
  abc_calendar: { state: "no_data", reason: "No stock items yet.", cells: [] },
  why_tree: { state: "no_data", reason: "No day to explain.", drivers: [] },
  alert_pyramid: { state: "no_data", reason: "No alerts.", levels: [] },
  door_cards: { state: "no_data", reason: "No doors yet.", doors: [] },
} as const;

it("every figure says when it has nothing to draw", () => {
  render(<GuideFigures figures={empty as never} />);
  for (const reason of ["No count yet.", "No stock yet.", "No order yet.", "No dish yet.", "No price change yet.", "No prices yet.", "No sales yet.", "No stock items yet.", "No day to explain.", "No alerts.", "No doors yet."]) {
    expect(screen.getAllByText(reason).length).toBeGreaterThan(0);
  }
});

it("a pareto payload and a traced order draw their series", () => {
  render(<GuideFigures figures={{
    ...empty,
    pareto: { state: "live", window: "last 30 days", points: [{ dish: "Tea", sales_kes: 150, cumulative_pct: 100 }] },
    shilling: { state: "live", steps: [{ step: "Order", detail: "Order 9 · KES 150 · mpesa" }, { step: "Statement", detail: "Receipt ABC" }] },
    three_way: { state: "as_entered", window: "latest cash count in the last 14 days", legs: [
      { key: "card", label: "Card", left_kes: 40, right_kes: null, left_label: "Card sales", right_label: "Settlement not recorded", look: false },
    ] },
  } as never} />);
  expect(screen.getByText("Tea")).toBeTruthy();
  expect(screen.getByText(/Order 9/)).toBeTruthy();
  expect(screen.getAllByText(/Settlement not recorded/).length).toBeGreaterThan(0);
});
