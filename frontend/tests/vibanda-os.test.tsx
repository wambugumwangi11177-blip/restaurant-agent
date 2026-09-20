import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import OsPage from "../src/app/vibanda/os/page";
import api from "@/lib/api";

vi.mock("@/lib/api", () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams() }));

const reply = {
  grounded: { finding: "Recorded revenue is KSh 500.", why: "Paid orders today.",
    impact: "—", recommendation: "Review recorded orders.", module: "revenue", steps: [] },
  llm_reply: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.get).mockResolvedValue({ data: {
    restaurant_name: "Vibanda Village", revenue: { revenue: 500, avg_order: 500 },
    orders: { orders: 1 }, bookings: { covers_today: 0 },
  } });
  vi.mocked(api.post).mockResolvedValue({ data: reply });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(cleanup);

function submit(question: string) {
  fireEvent.change(screen.getByLabelText("Your restaurant question"), { target: { value: question } });
  fireEvent.click(screen.getByRole("button", { name: "Send question" }));
}

describe("owner question flow", () => {
  it("shows the grounded answer without forced scrolling or an unrelated strategy call", async () => {
    render(<OsPage />);
    submit("How are sales today?");
    await screen.findByText(reply.grounded.finding);
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).toHaveBeenCalledWith("/api/v1/ai/chat", expect.objectContaining({
      question: "How are sales today?",
    }), { timeout: 45000 });
  });

  it("keeps failures visible instead of claiming that the restaurant is healthy", async () => {
    vi.mocked(api.post).mockRejectedValue(new Error("unavailable"));
    render(<OsPage />);
    submit("Is the kitchen running behind?");
    await screen.findByText("I couldn't complete that question.");
    expect(screen.queryByText(/Nothing urgent|No action needed|on pace/i)).toBeNull();
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
  });

  it("includes the previous answer when the owner asks a follow-up", async () => {
    render(<OsPage />);
    submit("How are sales today?");
    await screen.findByText(reply.grounded.finding);
    submit("What does that mean?");
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.post).mock.calls[1][1]).toEqual({
      question: "What does that mean?",
      history: [{ role: "user", content: "How are sales today?" },
        { role: "assistant", content: reply.grounded.finding }],
    });
  });
});
