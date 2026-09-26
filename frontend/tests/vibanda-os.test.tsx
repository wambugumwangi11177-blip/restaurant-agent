import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import OsPage from "../src/app/vibanda/os/page";
import api from "@/lib/api";

vi.mock("@/lib/api", () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams() }));

const reply = {
  module: "stock", grounded: { finding: "I can’t verify stock levels yet.", why: "No source records.", recommendation: "Connect stock records.", data: { available: false } },
  llm_reply: null, answer_text: "I can’t verify stock levels yet. Connect inventory quantities and stock movements.",
  answer_type: "restaurant_analysis", data_availability: "needs_connected_data",
  follow_up_prompts: ["What information needs to connect for this answer?"], conversation_id: 42,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.get).mockImplementation(async (url: string) => {
    if (url.endsWith("/ai/os/preferences")) return { data: { default_area: null } } as never;
    if (url.endsWith("/ai/os/conversations")) return { data: { conversations: [] } } as never;
    return { data: { data_provenance: { source_connection: { state: "awaiting_first_delivery", records: 0, reconciled: false } } } } as never;
  });
  vi.mocked(api.post).mockImplementation(async (url: string, payload?: unknown) => {
    if (url.endsWith("/ai/os/conversations")) return { data: { id: 42 } } as never;
    if ((payload as { topic?: string } | undefined)?.topic === "suppliers") return { data: { ...reply, answer_type: "planned_feature", data_availability: "planned_feature", answer_text: "The Suppliers page is planned and is not available yet." } } as never;
    return { data: reply } as never;
  });
  vi.mocked(api.put).mockResolvedValue({ data: { default_area: "money" } } as never);
  Object.defineProperty(globalThis.crypto, "randomUUID", { configurable: true, value: vi.fn(() => "message-uuid-1234") });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(cleanup);

function submit(question: string) {
  fireEvent.change(screen.getByLabelText("Ask or describe a change"), { target: { value: question } });
  fireEvent.click(screen.getByRole("button", { name: "Send question" }));
}

describe("owner OS without restaurant data", () => {
  it("opens with the starting questions and all four shared Home areas", async () => {
    render(<OsPage />);
    expect(screen.getByRole("heading", { name: /what would you like to work on/i })).toBeTruthy();
    expect(screen.getByText("Show me how this software can help my restaurant.")).toBeTruthy();
    expect(screen.getByText("Restaurant health")).toBeTruthy();
    expect(screen.getByText("Money and control")).toBeTruthy();
    expect(screen.getByText("Sales and risk")).toBeTruthy();
    expect(screen.getByText("Governance and setup")).toBeTruthy();
    expect(await screen.findByText(/Restaurant data isn’t connected yet/)).toBeTruthy();
  });

  it("searches planned questions and tells the owner their feature is not live", async () => {
    render(<OsPage />);
    fireEvent.change(screen.getByLabelText("Search all OS questions"), { target: { value: "Which supplier is most reliable?" } });
    const question = await screen.findByRole("button", { name: /Which supplier is most reliable.*Needs connected data.*Planned feature/i });
    fireEvent.click(question);
    await screen.findByText(/supplier.*planned and is not available yet/i);
    const chatCall = vi.mocked(api.post).mock.calls.find(([url]) => url.endsWith("/ai/chat"));
    expect(chatCall?.[1]).toMatchObject({ answer_mode: "analysis", topic: "suppliers", conversation_id: 42 });
  });

  it("submits a typed analytical question through auto routing and explains missing data", async () => {
    render(<OsPage />);
    submit("Which ingredients are running low? password=should-not-leak");
    await screen.findByText(reply.answer_text);
    expect(screen.getByText("Data needed before analysis")).toBeTruthy();
    expect(screen.getByText(/needs connected restaurant records/i)).toBeTruthy();
    const chatCall = vi.mocked(api.post).mock.calls.find(([url]) => url.endsWith("/ai/chat"));
    expect(chatCall?.[1]).toMatchObject({ question: "Which ingredients are running low? password: [removed]", answer_mode: "auto", conversation_id: 42, client_message_id: "message-uuid-1234" });
    expect(JSON.stringify(chatCall?.[1])).not.toContain("should-not-leak");
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
  });

  it("keeps the draft and retries the same turn without duplicating it", async () => {
    const chatReply = vi.mocked(api.post);
    chatReply.mockImplementationOnce(async () => ({ data: { id: 42 } } as never));
    chatReply.mockRejectedValueOnce(new Error("temporary network error"));
    chatReply.mockResolvedValueOnce({ data: reply } as never);
    render(<OsPage />);
    submit("Which ingredients are running low?");
    await screen.findByRole("button", { name: "Retry answer" });
    expect((screen.getByLabelText("Ask or describe a change") as HTMLTextAreaElement).value).toBe("Which ingredients are running low?");
    fireEvent.click(screen.getByRole("button", { name: "Retry answer" }));
    await screen.findByText(reply.answer_text);
    expect(screen.getAllByText("Which ingredients are running low?")).toHaveLength(1);
    const calls = chatReply.mock.calls.filter(([url]) => url.endsWith("/ai/chat"));
    expect(calls).toHaveLength(2);
    expect(calls[0][1]).toMatchObject({ client_message_id: "message-uuid-1234", conversation_id: 42, answer_mode: "auto" });
    expect(calls[1][1]).toEqual(calls[0][1]);
  });

  it("retains the current conversation for follow-ups", async () => {
    render(<OsPage />);
    submit("Which ingredients are running low?");
    await screen.findByText(reply.answer_text);
    submit("What information should I connect?");
    await waitFor(() => expect(vi.mocked(api.post).mock.calls.filter(([url]) => url.endsWith("/ai/chat"))).toHaveLength(2));
    const calls = vi.mocked(api.post).mock.calls.filter(([url]) => url.endsWith("/ai/chat"));
    expect(calls[0][1]).toMatchObject({ conversation_id: 42 });
    expect(calls[1][1]).toMatchObject({ conversation_id: 42, question: "What information should I connect?" });
  });

  it("loads a saved conversation from the previous conversations list", async () => {
    const savedAnswer = { ...reply, answer_text: "The stored answer is general guidance." };
    vi.mocked(api.get).mockImplementation(async (url: string) => {
      if (url.endsWith("/ai/os/preferences")) return { data: { default_area: null } } as never;
      if (url.endsWith("/ai/os/conversations")) return { data: { conversations: [{ id: 7, title: "Saved stock question", updated_at: "2026-09-25T10:00:00Z" }] } } as never;
      if (url.endsWith("/ai/os/conversations/7")) return { data: { id: 7, messages: [
        { id: 1, role: "user", content: "Saved stock question" },
        { id: 2, role: "assistant", content: JSON.stringify(savedAnswer) },
      ] } } as never;
      return { data: { data_provenance: { source_connection: { state: "awaiting_first_delivery", reconciled: false } } } } as never;
    });
    render(<OsPage />);
    fireEvent.click(screen.getByRole("button", { name: "Previous conversations" }));
    fireEvent.click(await screen.findByRole("button", { name: /Saved stock question/ }));
    expect(await screen.findByText("Saved stock question")).toBeTruthy();
    expect(await screen.findByText("The stored answer is general guidance.")).toBeTruthy();
  });

  it("previews and saves the OS default area only after Apply", async () => {
    render(<OsPage />);
    const moneyDetails = screen.getByText("Money and control").closest("details")!;
    fireEvent.click(moneyDetails.querySelector("summary")!);
    fireEvent.click((await within(moneyDetails).findAllByRole("button", { name: "Make my default" }))[0]);
    expect(screen.getByRole("dialog", { name: "Preview default OS area" })).toBeTruthy();
    expect(screen.getByText("After: Money and control")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Apply preference" }));
    await screen.findByText("Your default area is saved.");
    expect(api.put).toHaveBeenCalledWith("/api/v1/ai/os/preferences", { default_area: "money" });
  });
});
