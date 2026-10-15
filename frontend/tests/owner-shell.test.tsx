import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import OwnerShell from "@/components/owner/OwnerShell";

const nav = vi.hoisted(() => ({ replace: vi.fn(), pathname: "/home" }));
const auth = vi.hoisted(() => ({ value: { user: null as null | Record<string, unknown>, isLoading: false } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: nav.replace, push: vi.fn() }), usePathname: () => nav.pathname }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => auth.value }));
vi.mock("@/components/NotificationBell", () => ({ default: () => <span data-testid="bell" /> }));

const owner = (tenant_name: string) => ({ id: 1, email: "o@x.test", role: "admin", staff_role: "owner", tenant_name, restaurant_name: tenant_name });

beforeEach(() => { vi.clearAllMocks(); nav.pathname = "/home"; });
afterEach(cleanup);

function pages() {
  return within(screen.getAllByRole("navigation", { name: "Owner pages" })[0]).getAllByRole("link").map((a) => a.textContent?.trim());
}

it("an owner sees Home, Ask LEVIII and Reports, with the current page marked", () => {
  auth.value = { user: owner("Mama Oliech"), isLoading: false };
  nav.pathname = "/reports";
  render(<OwnerShell><p>page body</p></OwnerShell>);
  expect(pages()).toEqual(["Home", "Ask LEVIII", "Reports", "Operations"]);
  const current = screen.getAllByRole("link", { current: "page" });
  expect(current.length).toBeGreaterThan(0);
  expect(current.every((a) => a.textContent?.includes("Reports"))).toBe(true);
  expect(screen.getByText("page body")).toBeTruthy();
});

it("Vibanda and the Demo Restaurant have no way into the operational screens, and the Demo says it is made up", () => {
  auth.value = { user: owner("Vibanda Village"), isLoading: false };
  const { unmount } = render(<OwnerShell>x</OwnerShell>);
  expect(pages()).toEqual(["Home", "Ask LEVIII", "Reports"]);
  unmount();
  auth.value = { user: owner("Demo Restaurant"), isLoading: false };
  render(<OwnerShell>x</OwnerShell>);
  expect(pages()).toEqual(["Home", "Ask LEVIII", "Reports"]);
  expect(screen.getByText(/made-up restaurant/)).toBeTruthy();
});

it("the date is the Nairobi date and the shell is keyboard-navigable (two named navs, links not buttons)", () => {
  auth.value = { user: owner("Mama Oliech"), isLoading: false };
  render(<OwnerShell>x</OwnerShell>);
  expect(screen.getByText(/· Nairobi$/)).toBeTruthy();
  expect(screen.getAllByRole("navigation", { name: "Owner pages" })).toHaveLength(2);
});

it("a signed-out visitor goes to login and a manager to their own screens; neither sees the owner's figures", () => {
  auth.value = { user: null, isLoading: false };
  const { unmount } = render(<OwnerShell><p>secret figures</p></OwnerShell>);
  expect(nav.replace).toHaveBeenCalledWith("/login");
  expect(screen.queryByText("secret figures")).toBeNull();
  unmount();
  auth.value = { user: { id: 2, email: "m@x.test", role: "staff", staff_role: "manager", tenant_name: "Mama Oliech" }, isLoading: false };
  render(<OwnerShell><p>secret figures</p></OwnerShell>);
  expect(nav.replace).toHaveBeenCalledWith("/staff/manager");
  expect(screen.queryByText("secret figures")).toBeNull();
});

it("says it is checking while the account is still loading, and routes nobody yet", () => {
  auth.value = { user: null, isLoading: true };
  render(<OwnerShell>x</OwnerShell>);
  expect(screen.getByRole("status").textContent).toMatch(/Checking account access/);
  expect(nav.replace).not.toHaveBeenCalled();
});
