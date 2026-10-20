import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import BandForecast from "@/components/charts/BandForecast";
import Bars from "@/components/charts/Bars";
import BreakEvenClock from "@/components/charts/BreakEvenClock";
import CashRunway from "@/components/charts/CashRunway";
import ChartEmpty from "@/components/charts/ChartEmpty";
import Dial from "@/components/charts/Dial";
import HBars from "@/components/charts/HBars";
import HeatGrid from "@/components/charts/HeatGrid";
import Quadrant from "@/components/charts/Quadrant";
import ShiftTable from "@/components/charts/ShiftTable";
import Sparkline from "@/components/charts/Sparkline";
import StackedBar from "@/components/charts/StackedBar";
import Waterfall from "@/components/charts/Waterfall";

afterEach(cleanup);

describe("every chart says what it has not got instead of drawing something", () => {
  it("no_data, unavailable and learning each give their own words, and learning shows how far along it is", () => {
    const { rerender } = render(<ChartEmpty state="no_data" reason="No sales recorded yet." />);
    expect(screen.getByRole("status").textContent).toContain("No sales recorded yet.");
    rerender(<ChartEmpty state="unavailable" />);
    expect(screen.getByRole("status").textContent).toContain("Not available yet.");
    rerender(<ChartEmpty state="learning" day={9} of={30} reason="Needs four weeks of cash counts." />);
    expect(screen.getByRole("status").textContent).toContain("Learning · day 9 of 30");
  });

  it.each([
    ["Bars", <Bars key="b" bars={[]} label="x" />],
    ["HBars", <HBars key="h" rows={[]} label="x" />],
    ["Dial", <Dial key="d" value={1} target={2} label="x" word="Fine" tone="good" state="no_data" reason="Nothing yet." />],
    ["StackedBar", <StackedBar key="s" segments={[]} label="x" />],
    ["Waterfall", <Waterfall key="w" steps={[]} label="x" />],
    ["BandForecast", <BandForecast key="f" actual={[]} next={[]} label="x" />],
    ["Quadrant", <Quadrant key="q" dishes={[]} label="x" />],
    ["BreakEvenClock", <BreakEvenClock key="c" breakEven={0} soldSoFar={5} coveredAt={null} label="x" />],
    ["CashRunway", <CashRunway key="r" days={[]} label="x" />],
    ["ShiftTable", <ShiftTable key="t" rows={[]} label="x" />],
    ["HeatGrid", <HeatGrid key="g" cells={[]} label="x" state="learning" day={5} of={28} />],
  ])("%s with nothing to show draws no chart", (_name, node) => {
    render(node);
    expect(screen.getByRole("status")).toBeTruthy();
    expect(document.querySelector("svg")).toBeNull();
  });
});

describe("Bars", () => {
  const bars = [{ key: "a", label: "Fri", value: 100, title: "Fri: KES 100" }, { key: "b", label: "Sat", value: 50, title: "Sat: KES 50", highlight: true }, { key: "c", label: "Sun", value: 0, title: "Sun: none" }];
  it("starts every bar at zero: a half-size number is a half-height bar", () => {
    render(<Bars bars={bars} label="Sales" format={(v) => `${v}`} />);
    const rects = [...document.querySelectorAll("rect")];
    const heights = rects.map((r) => Number(r.getAttribute("height")));
    expect(heights[1] / heights[0]).toBeCloseTo(0.5, 2);
    expect(heights[2]).toBe(0);
    expect(screen.getByRole("img", { name: "Sales" })).toBeTruthy();
    expect(document.querySelectorAll("title")).toHaveLength(3);
  });
});

describe("HBars", () => {
  it("draws against the largest row (or a given max) and flags the rows to look at", () => {
    render(<HBars label="What each dish earns" rows={[{ key: "1", label: "Nyama choma", value: 60, valueLabel: "KES 60", flag: true }, { key: "2", label: "Stew", value: 30, valueLabel: "KES 30" }]} />);
    const list = screen.getByRole("list", { name: "What each dish earns" });
    const widths = [...list.querySelectorAll<HTMLElement>("[style*='width']")].map((e) => e.style.width);
    expect(widths).toEqual(["100%", "50%"]);
    expect(within(list).getByText("KES 60").className).toContain("destructive");
  });
  it("a percentage is drawn against 100, not against the biggest row", () => {
    render(<HBars label="x" max={100} rows={[{ key: "1", label: "A", value: 20, valueLabel: "20%" }]} />);
    expect((document.querySelector("[style*='width']") as HTMLElement).style.width).toBe("20%");
  });
});

describe("Dial", () => {
  it("says the number, the owner's word and the owner's target, and puts the marker where the value is", () => {
    render(<Dial value={29.3} target={35} label="Out of every KES 100, ingredients" word="Fine" tone="good" />);
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe("Out of every KES 100, ingredients: 29.3%, Fine. Your target is 35%.");
    expect(screen.getByText("Your target: 35%", { exact: false })).toBeTruthy();
    expect(screen.getByText("29.3%")).toBeTruthy();
  });
  it("the green band ends exactly at the owner's target", () => {
    render(<Dial value={20} target={35} max={70} label="x" word="Fine" tone="good" />);
    const [green] = [...document.querySelectorAll("path")];
    const [x1, y1] = green.getAttribute("d")!.split("A")[1].trim().split(" ").slice(-2).map(Number);
    const angle = (Math.atan2(100 - y1, x1 - 100) * 180) / Math.PI;                       // 90° is straight up: half way along a 0–70 scale
    expect(angle).toBeCloseTo(90, 0);
  });
  it("a value far over the target still sits on the scale (never off the end of the dial)", () => {
    render(<Dial value={90} target={35} max={60} label="x" word="High" tone="bad" />);
    const marker = document.querySelector("circle") as SVGCircleElement;
    expect(Number(marker.getAttribute("cx"))).toBeLessThanOrEqual(180.01);
    expect(Number(marker.getAttribute("cx"))).toBeGreaterThanOrEqual(19.99);
  });
});

describe("StackedBar", () => {
  it("draws shares in proportion and lists every one in words", () => {
    render(<StackedBar label="Out of every KES 100 you take" segments={[
      { key: "i", label: "Ingredients", value: 30, color: "red" }, { key: "w", label: "Wages", value: 20, color: "blue" }, { key: "k", label: "What you kept", value: 50, color: "green" }]} />);
    const parts = [...document.querySelectorAll<HTMLElement>("[role=img] > div")].map((d) => d.style.width);
    expect(parts).toEqual(["30%", "20%", "50%"]);
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain("What you kept 50");
  });
  it("a loss is not drawn as a negative width: it is said in words", () => {
    render(<StackedBar label="x" segments={[{ key: "i", label: "Ingredients", value: 60, color: "red" }, { key: "k", label: "What you kept", value: -5, color: "green" }]} />);
    expect(document.querySelectorAll("[role=img] > div")).toHaveLength(1);
    expect(screen.getByText(/What you kept went below zero/)).toBeTruthy();
  });
});

describe("Waterfall", () => {
  const steps = [
    { key: "sales", label: "Sales", value: 412000, kind: "start" as const, valueLabel: "KES 412,000" },
    { key: "ing", label: "Ingredients", value: 131800, kind: "minus" as const, valueLabel: "KES 131,800" },
    { key: "left", label: "Left after ingredients", value: 280200, kind: "subtotal" as const, valueLabel: "KES 280,200" },
    { key: "kept", label: "What you kept", value: 65200, kind: "end" as const, valueLabel: "KES 65,200" },
  ];
  it("costs float off the end of what came in, and every row says its amount", () => {
    render(<Waterfall label="Profit and loss" steps={steps} />);
    const rows = within(screen.getByRole("list", { name: "Profit and loss" })).getAllByRole("listitem");
    expect(rows).toHaveLength(4);
    const bar = (i: number) => rows[i].querySelector<HTMLElement>("span[style]")!;
    expect(bar(0).style.left).toBe("0%");
    expect(parseFloat(bar(1).style.left)).toBeCloseTo(68.0, 0);                                        // starts where what is left starts …
    expect(parseFloat(bar(1).style.width)).toBeCloseTo(32.0, 0);                                       // … and is as wide as the cost
    expect(parseFloat(bar(1).style.left) + parseFloat(bar(1).style.width)).toBeCloseTo(100, 1);       // ends where sales ended
    expect(within(rows[1]).getByText("− KES 131,800")).toBeTruthy();
    expect(within(rows[3]).getByText("KES 65,200")).toBeTruthy();
  });
  it("a loss is drawn left of a zero line and in red", () => {
    render(<Waterfall label="x" steps={[{ key: "s", label: "Sales", value: 100, kind: "start", valueLabel: "KES 100" }, { key: "c", label: "Costs", value: 130, kind: "minus", valueLabel: "KES 130" }, { key: "k", label: "What you kept", value: -30, kind: "end", valueLabel: "-KES 30" }]} />);
    const last = screen.getAllByRole("listitem")[2];
    expect(last.querySelector("span[style*='destructive']")).toBeTruthy();
    expect(last.querySelector("span.w-px")).toBeTruthy();
    expect(within(last).getByText("-KES 30").className).toContain("destructive");
  });
});

describe("Sparkline", () => {
  it("draws a line for two or more points and nothing for fewer", () => {
    const { rerender } = render(<Sparkline values={[1, 3, 2]} label="Last 3 days" />);
    expect(screen.getByRole("img", { name: "Last 3 days" })).toBeTruthy();
    rerender(<Sparkline values={[5]} label="one" />);
    expect(document.querySelector("svg")).toBeNull();
  });
  it("a flat line does not divide by zero", () => {
    render(<Sparkline values={[4, 4, 4]} label="flat" />);
    expect(document.querySelector("polyline")!.getAttribute("points")).not.toMatch(/NaN|Infinity/);
  });
});

describe("BandForecast", () => {
  const actual = Array.from({ length: 14 }, (_, i) => ({ date: `2026-10-${String(i + 1).padStart(2, "0")}`, sales: 15000 + i * 300 }));
  const next = Array.from({ length: 7 }, (_, i) => ({ date: `2026-10-${String(i + 15).padStart(2, "0")}`, usual: 20000, low: 17000, high: 24000 }));
  it("draws what sold, the usual and a band, with the unusual days marked and explained", () => {
    render(<BandForecast actual={actual} next={next} unusual={[{ date: "2026-10-05", sales: 25000, expected: 14000 }]} label="Sales and the next 7 days" />);
    const svg = screen.getByRole("img", { name: "Sales and the next 7 days" });
    expect(svg.querySelectorAll("path").length).toBeGreaterThanOrEqual(3);
    expect(within(svg).getByText(/Likely range for the next 7 days/)).toBeTruthy();
    expect(within(svg).getByText(/25000 against about 14000 expected/)).toBeTruthy();
    expect(svg.innerHTML).not.toMatch(/NaN/);
  });
  it("with history only (no forecast yet) it still draws the line", () => {
    render(<BandForecast actual={actual} next={[]} label="x" />);
    expect(document.querySelector("svg")).toBeTruthy();
    expect(document.querySelector("svg")!.innerHTML).not.toMatch(/NaN/);
  });
});

describe("Quadrant", () => {
  const dishes = [
    { name: "Nyama choma", sold: 59, earns: 1040, kind: "Best dish" },
    { name: "Chips", sold: 80, earns: 120, kind: "Popular, earns little" },
    { name: "Fish", sold: 5, earns: 900, kind: "Earns well, few order it" },
    { name: "Soup", sold: 3, earns: 60, kind: "Consider removing" },
  ];
  it("one dot per dish, each in the colour and corner of its word, and each explained on hover", () => {
    render(<Quadrant dishes={dishes} label="Your dishes" />);
    const svg = screen.getByRole("img", { name: "Your dishes" });
    expect(svg.querySelectorAll("circle")).toHaveLength(4);
    for (const k of ["Best dish", "Popular, earns little", "Earns well, few order it", "Consider removing"]) expect(within(svg).getAllByText(new RegExp(k)).length).toBeGreaterThan(0);
    expect(within(svg).getByText("Chips: 80 sold, earns KES 120 a plate · Popular, earns little")).toBeTruthy();
  });
  it("sells more is further right and earns more a plate is higher", () => {
    render(<Quadrant dishes={dishes} label="x" />);
    const [best, chips, fish] = [...document.querySelectorAll("circle")];
    expect(Number(chips.getAttribute("cx"))).toBeGreaterThan(Number(best.getAttribute("cx")));
    expect(Number(fish.getAttribute("cy"))).toBeLessThan(Number(chips.getAttribute("cy")));
  });
});

describe("BreakEvenClock", () => {
  it("says how much is still to go while the day has not covered its costs", () => {
    render(<BreakEvenClock breakEven={5000} soldSoFar={1250} coveredAt={null} label="Costs covered" />);
    expect(screen.getByText("KES 3,750 to go")).toBeTruthy();
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe("Costs covered: KES 3,750 to go");
    const ring = document.querySelectorAll("circle")[1];
    expect(ring.getAttribute("stroke")).toContain("primary");
  });
  it("turns green and says when once covered, and a full ring never overflows", () => {
    render(<BreakEvenClock breakEven={4946} soldSoFar={22290} coveredAt="12:31 pm" label="Costs covered" />);
    expect(screen.getByText("Covered at 12:31 pm")).toBeTruthy();
    const ring = document.querySelectorAll("circle")[1];
    expect(ring.getAttribute("stroke")).toContain("good");
    const [filled, whole] = ring.getAttribute("stroke-dasharray")!.split(" ").map(Number);
    expect(filled).toBeCloseTo(whole, 1);
  });
});

describe("CashRunway", () => {
  const days = [
    { date: "2026-10-15", balance: 15000, bills: 0 }, { date: "2026-10-16", balance: 29000, bills: 0 }, { date: "2026-10-17", balance: 43000, bills: 0 },
    { date: "2026-10-18", balance: -19000, bills: 70000 }, { date: "2026-10-19", balance: -5000, bills: 0 }, { date: "2026-10-20", balance: 8000, bills: 0 },
  ];
  it("says how many days would be short, marks each bill, and draws the shortfall below the zero line", () => {
    render(<CashRunway days={days} label="Cash over the next 30 days" />);
    const svg = screen.getByRole("img");
    expect(svg.getAttribute("aria-label")).toBe("Cash over the next 30 days: short on 2 of the next 6 days");
    expect(svg.querySelectorAll("circle")).toHaveLength(1);
    expect(within(svg as unknown as HTMLElement).getByText(/bills KES 70,000, left -KES 19,000/)).toBeTruthy();
    expect(svg.innerHTML).not.toMatch(/NaN/);
  });
  it("with enough for every bill it says so", () => {
    render(<CashRunway days={days.map((d) => ({ ...d, balance: Math.abs(d.balance) }))} label="Cash" />);
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe("Cash: enough for every bill");
  });
});

describe("ShiftTable", () => {
  const rows = [
    { key: "1", when: "Thu 15 Oct · morning", expected: 1720, counted: 1710, gap: -10, check: false },
    { key: "2", when: "Tue 13 Oct · evening", expected: 4000, counted: 3500, gap: -500, check: true },
    { key: "3", when: "Mon 12 Oct · evening", expected: 3000, counted: 3000, gap: 0, check: false },
  ];
  it("shows each count against what the till says, flags the shift to look at, and says Matches when it matches", () => {
    render(<ShiftTable rows={rows} label="Cash counts" />);
    const table = screen.getByRole("table", { name: "Cash counts" });
    const flagged = within(table).getAllByRole("row").filter((r) => r.getAttribute("data-check") === "true");
    expect(flagged).toHaveLength(1);
    expect(within(flagged[0]).getByText("Look at this")).toBeTruthy();
    expect(within(flagged[0]).getByText("Short KES 500")).toBeTruthy();
    expect(within(table).getByText("Matches")).toBeTruthy();
    expect(within(table).getByText("Short KES 10").className).toContain("destructive");
  });
});

describe("HeatGrid", () => {
  it("fills only the shifts that repeat, darker the more often they were short", () => {
    render(<HeatGrid label="Shifts that repeat" cells={[{ weekday: 1, shift: "evening", timesShort: 4, ofLast: 4, title: "Tuesday evening: short 4 of the last 4" }]} />);
    const table = screen.getByRole("table", { name: "Shifts that repeat" });
    expect(within(table).getByText("4/4")).toBeTruthy();
    expect(within(table).getAllByRole("columnheader").map((c) => c.textContent)).toEqual(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]);
    expect(table.querySelector("[title='Tuesday evening: short 4 of the last 4']")).toBeTruthy();
    expect(table.querySelectorAll("div[title='']")).toHaveLength(13);                      // every other cell is quiet
  });
});
