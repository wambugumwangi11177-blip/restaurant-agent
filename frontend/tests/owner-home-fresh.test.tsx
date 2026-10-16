import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import HomePage from "../src/app/(owner)/home/page";
import api from "@/lib/api";
import fresh from "./fixtures/owner/home_fresh.json";

vi.mock("@/lib/api", () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: { restaurant_name: "Mama Oliech", tenant_name: "Mama Oliech" } }) }));
vi.mock("next/link", () => ({ default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => <a href={href} {...rest}>{children}</a> }));

beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.get).mockResolvedValue({ data: structuredClone(fresh) } as never); window.location.hash = ""; });
afterEach(cleanup);

it("a restaurant with nothing recorded gets a Home that says so, zone by zone, and never throws", async () => {
  render(<HomePage />);
  expect(await screen.findByText("No sale recorded yet.")).toBeTruthy();
  expect(screen.getAllByText("Nothing recorded yet").length).toBeGreaterThan(0);                 // the state chips say it in words
  expect(screen.getByText(/Nothing is costing you money that we can see/)).toBeTruthy();
  expect(document.body.textContent).not.toMatch(/NaN|undefined|Infinity|\[object/);
});

it("every one of the six panels opens on an empty restaurant, gives a reason, and draws no chart", async () => {
  render(<HomePage />);
  await screen.findByText("No sale recorded yet.");
  for (const name of ["My Money", "Sales & Dishes", "Store & Suppliers", "Cash Check", "Staff", "Permits & Settings"]) {
    fireEvent.click(screen.getByRole("button", { name: new RegExp(name) }));
    const body = screen.getByRole("region", { name });
    expect(within(body).getAllByRole("status").length).toBeGreaterThan(0);
    expect(body.querySelector("svg")).toBeNull();
  }
  expect(document.body.textContent).not.toMatch(/NaN|undefined|Infinity|\[object/);
});

it("an empty restaurant's Home still offers the way forward: coming up says what is not there, not an error", async () => {
  render(<HomePage />);
  const zone = (await screen.findByRole("heading", { name: "Coming up" })).closest("section")!;
  expect(within(zone).getAllByText(/No |Nothing|Add/).length).toBeGreaterThanOrEqual(4);
  expect(screen.queryByRole("alert")).toBeNull();
});
