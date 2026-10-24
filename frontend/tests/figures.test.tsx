import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import BreakEvenLine from "@/components/charts/BreakEvenLine";
import CheckMatrix from "@/components/charts/CheckMatrix";
import TenderMix from "@/components/charts/TenderMix";
import ToleranceCurve from "@/components/charts/ToleranceCurve";

afterEach(cleanup);

it("the break-even line names the crossing time from the sales already recorded", () => {
  render(<BreakEvenLine points={[{ at: "10:00 am", sales: 4000 }, { at: "12:31 pm", sales: 9000 }]} breakEven={8000} coveredAt="12:31 pm" toGo={0} />);
  expect(screen.getByRole("img", { name: /costs this day has to cover/ })).toBeTruthy();
  expect(screen.getByText(/Sales crossed that line at 12:31 pm/)).toBeTruthy();
});

it("an empty tender mix says what will appear once an order is paid", () => {
  render(<TenderMix tenders={[]} />);
  expect(screen.getByRole("status").textContent).toMatch(/cash, M-Pesa and card/);
});

it("the tolerance curve draws from the owner's own limit when no count exists yet", () => {
  render(<ToleranceCurve toleranceKes={200} tolerancePct={1} dots={[]} />);
  expect(screen.getByRole("img", { name: "Cash difference you accept" })).toBeTruthy();
  expect(screen.getByText(/No counts yet/)).toBeTruthy();
});

it("the check matrix stays quiet until a check finds something", () => {
  render(<CheckMatrix counts={{ cash: 0, cancelled: 0, mpesa: 0, price: 0, stock: 0 }} />);
  expect(screen.getAllByText("Catches it").length).toBeGreaterThan(0);
  expect(screen.getByText(/Nothing to look at/)).toBeTruthy();
});
