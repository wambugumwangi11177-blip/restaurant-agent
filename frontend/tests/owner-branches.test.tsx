import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import BranchPicker, { branchLabel } from "@/components/owner/BranchPicker";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ default: api }));

const reload = vi.fn();
beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(window, "location", { value: { ...window.location, reload }, writable: true });
});
afterEach(cleanup);

const demo = [
  { id: 1, name: "Demo Restaurant", address: "Westlands, Nairobi", is_active: false },
  { id: 2, name: "Demo Restaurant – Kasarani", address: "Kasarani, Nairobi", is_active: true },
];

it("an owner with two branches sees both, named by place, with the one the screens are about chosen", async () => {
  api.get.mockResolvedValue({ data: demo });
  render(<BranchPicker />);
  const select = (await screen.findByRole("combobox", { name: /Branch/ })) as HTMLSelectElement;
  expect([...select.options].map((o) => o.textContent)).toEqual(["Demo Restaurant · Westlands", "Demo Restaurant – Kasarani"]);
  expect(select.value).toBe("2");
});

it("choosing the other branch selects it on the server and reloads every block for it", async () => {
  api.get.mockResolvedValue({ data: demo });
  api.post.mockResolvedValue({ data: {} });
  render(<BranchPicker />);
  fireEvent.change(await screen.findByRole("combobox", { name: /Branch/ }), { target: { value: "1" } });
  await waitFor(() => expect(reload).toHaveBeenCalled());
  expect(api.post).toHaveBeenCalledWith("/restaurants/select", { restaurant_id: 1 });
});

it("one branch, or a list the user may not read, shows nothing", async () => {
  api.get.mockResolvedValue({ data: [demo[0]] });
  const { container, unmount } = render(<BranchPicker />);
  await waitFor(() => expect(api.get).toHaveBeenCalled());
  expect(container.innerHTML).toBe("");
  unmount();
  api.get.mockRejectedValue(new Error("403"));
  const again = render(<BranchPicker />);
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  expect(again.container.innerHTML).toBe("");
});

it("a name that already says its place is left alone", () => {
  expect(branchLabel({ name: "Eleven Kilimani", address: "Kilimani, Nairobi" })).toBe("Eleven Kilimani");
  expect(branchLabel({ name: "Eleven", address: null })).toBe("Eleven");
});
