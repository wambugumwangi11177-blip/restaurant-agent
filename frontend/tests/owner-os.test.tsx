import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import OsPage from "../src/app/(owner)/os/page";
import api from "@/lib/api";
import money from "./fixtures/owner/ask_what.json";
import compare from "./fixtures/owner/ask_compare_branches.json";
import type { OwnerAnswer } from "@/lib/owner/ask";

const navigationState = vi.hoisted(() => ({ query: "", tenant: "Demo Restaurant" }));
vi.mock("@/lib/api", () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: { restaurant_name: "Mama Oliech", tenant_name: navigationState.tenant } }) }));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(navigationState.query) }));

const answer = (over: Partial<OwnerAnswer> = {}): OwnerAnswer => ({ ...(money as unknown as OwnerAnswer), conversation_id: 42, ...over });
const chatReply = {
  module: "ops", grounded: { finding: "x" }, llm_reply: null, answer_text: "Here is how the software can help.", answer_type: "capability_explanation",
  follow_up_prompts: ["Which part of the software would you like explained?"], conversation_id: 42,
};
const asks = () => vi.mocked(api.post).mock.calls.filter(([url]) => url.endsWith("/owner/ask"));
const chats = () => vi.mocked(api.post).mock.calls.filter(([url]) => url.endsWith("/ai/chat"));

beforeEach(() => {
  vi.clearAllMocks();
  navigationState.query = "";
  navigationState.tenant = "Demo Restaurant";
  vi.mocked(api.get).mockImplementation(async (url: string) => {
    if (url.endsWith("/ai/os/conversations")) return { data: { conversations: [] } } as never;
    return { data: { data_provenance: { source_connection: { state: "receiving", reconciled: true } } } } as never;
  });
  vi.mocked(api.post).mockImplementation(async (url: string) => {
    if (url.endsWith("/ai/os/conversations")) return { data: { id: 42 } } as never;
    if (url.endsWith("/ai/chat")) return { data: chatReply } as never;
    return { data: answer() } as never;
  });
  Object.defineProperty(globalThis.crypto, "randomUUID", { configurable: true, value: vi.fn(() => "message-uuid-1234") });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(cleanup);

function submit(question: string) {
  fireEvent.change(screen.getByLabelText("Ask or describe a change"), { target: { value: question } });
  fireEvent.click(screen.getByRole("button", { name: "Send question" }));
}

describe("Ask LEVIII in five forms", () => {
  it("opens with the five forms to try and no label that says a feature is not live", async () => {
    render(<OsPage />);
    expect(screen.getByRole("heading", { name: /what would you like to work on/i })).toBeTruthy();
    for (const form of ["What", "Why", "What if", "What should I do", "Compare"]) expect(screen.getAllByText(form, { exact: true }).length).toBeGreaterThan(0);
    const body = document.body.textContent ?? "";
    for (const bad of ["Planned feature", "Needs connected data", "planned and is not available", "Vibanda"]) expect(body).not.toContain(bad);
    expect(screen.getByText("Show me how this software can help my restaurant.")).toBeTruthy();
  });

  it("a question about the owner's figures goes to the five forms and its answer is drawn as a card", async () => {
    render(<OsPage />);
    submit("Am I making a profit this month?");
    expect(await screen.findByText(money.headline)).toBeTruthy();
    expect(asks()).toHaveLength(1);
    expect(asks()[0][1]).toEqual({ question: "Am I making a profit this month?", conversation_id: 42, client_message_id: "message-uuid-1234" });   // no form: the words choose it
    expect(chats()).toHaveLength(0);
  });

  it("the form the owner picks is the form that is asked for", async () => {
    render(<OsPage />);
    fireEvent.click(screen.getByRole("radio", { name: "Why" }));
    expect(screen.getByRole("radio", { name: "Why" }).getAttribute("aria-checked")).toBe("true");
    submit("sales on Tuesday");
    await screen.findByText(money.headline);
    expect(asks()[0][1]).toMatchObject({ question: "sales on Tuesday", form: "why" });
  });

  it("a tried question is asked in the form of its group", async () => {
    render(<OsPage />);
    const group = screen.getByText("What if", { selector: "span.block" }).closest("details")!;
    fireEvent.click(group.querySelector("summary")!);
    fireEvent.click(within(group).getByRole("button", { name: "What if I cut Burger by 10%?" }));
    await screen.findByText(money.headline);
    expect(asks()[0][1]).toMatchObject({ question: "What if I cut Burger by 10%?", form: "what_if" });
  });

  it("a request for help or an explanation goes to the writing assistant, not the five forms", async () => {
    render(<OsPage />);
    fireEvent.click(screen.getByRole("button", { name: /Show me how this software can help/ }));
    expect(await screen.findByText(chatReply.answer_text)).toBeTruthy();
    expect(chats()[0][1]).toMatchObject({ question: "Show me how this software can help my restaurant.", answer_mode: "capabilities", conversation_id: 42 });
    expect(asks()).toHaveLength(0);
    cleanup();
    render(<OsPage />);
    submit("Can you help with a creative idea?");
    await screen.findByText(chatReply.answer_text);
    expect(chats().at(-1)?.[1]).toMatchObject({ answer_mode: "auto" });
  });

  it("lets a linked question use the same routing as a typed one", async () => {
    navigationState.query = "q=Who%20should%20I%20win%20back%3F";
    render(<OsPage />);
    await screen.findByText(money.headline);
    expect(asks()[0][1]).toMatchObject({ question: "Who should I win back?" });
    cleanup();
    navigationState.query = "q=Can%20you%20help%20with%20a%20creative%20idea%3F";
    render(<OsPage />);
    await screen.findByText(chatReply.answer_text);
    expect(chats().at(-1)?.[1]).toMatchObject({ question: "Can you help with a creative idea?", answer_mode: "auto" });
  });

  it("follow-up questions on an answer are asked in the same conversation", async () => {
    vi.mocked(api.post).mockImplementation(async (url: string) =>
      (url.endsWith("/ai/os/conversations") ? { data: { id: 42 } } : { data: answer({ next: ["Compare my branches"] }) }) as never);
    render(<OsPage />);
    submit("Am I making a profit this month?");
    fireEvent.click(await screen.findByRole("button", { name: "Compare my branches" }));
    await waitFor(() => expect(asks()).toHaveLength(2));
    expect(asks()[1][1]).toMatchObject({ question: "Compare my branches", conversation_id: 42 });
    expect(vi.mocked(api.post).mock.calls.filter(([url]) => url.endsWith("/ai/os/conversations"))).toHaveLength(1);
  });

  it("removes anything that looks like a credential before it is sent", async () => {
    render(<OsPage />);
    submit("Am I making a profit? password=should-not-leak");
    await screen.findByText(money.headline);
    expect(asks()[0][1]).toMatchObject({ question: "Am I making a profit? password: [removed]" });
    expect(JSON.stringify(asks()[0][1])).not.toContain("should-not-leak");
  });

  it("keeps the draft and retries the same turn without duplicating it", async () => {
    const post = vi.mocked(api.post);
    post.mockImplementationOnce(async () => ({ data: { id: 42 } } as never));
    post.mockRejectedValueOnce(new Error("temporary network error"));
    post.mockResolvedValueOnce({ data: answer() } as never);
    render(<OsPage />);
    submit("Am I making a profit this month?");
    await screen.findByRole("button", { name: "Retry answer" });
    expect((screen.getByLabelText("Ask or describe a change") as HTMLTextAreaElement).value).toBe("Am I making a profit this month?");
    fireEvent.click(screen.getByRole("button", { name: "Retry answer" }));
    await screen.findByText(money.headline);
    expect(within(screen.getByRole("region", { name: "Conversation messages" })).getAllByText("Am I making a profit this month?")).toHaveLength(1);
    expect(asks()).toHaveLength(2);
    expect(asks()[1][1]).toEqual(asks()[0][1]);                                              // same client_message_id: the server will not work it out twice
  });

  it("preserves reading position when the owner scrolls while an answer is pending", async () => {
    let finish!: (value: { data: OwnerAnswer }) => void;
    const pending = new Promise<{ data: OwnerAnswer }>((resolve) => { finish = resolve; });
    vi.mocked(api.post).mockResolvedValueOnce({ data: { id: 42 } } as never);
    vi.mocked(api.post).mockImplementationOnce(() => pending as never);
    render(<OsPage />);
    submit("Am I making a profit this month?");
    const viewport = await screen.findByRole("region", { name: "Conversation messages" });
    Object.defineProperties(viewport, {
      scrollHeight: { configurable: true, value: 1200 }, clientHeight: { configurable: true, value: 400 },
      scrollTop: { configurable: true, writable: true, value: 200 },
    });
    fireEvent.scroll(viewport);
    await act(async () => { finish({ data: answer() }); });
    expect(await screen.findByRole("button", { name: /New response/ })).toBeTruthy();
    expect(viewport.scrollTop).toBe(200);
    viewport.scrollTop = 800;
    fireEvent.scroll(viewport);
    expect(screen.queryByRole("button", { name: /New response/ })).toBeNull();
  });

  it("loads a saved conversation, drawing our answers as cards and older chat replies as text", async () => {
    vi.mocked(api.get).mockImplementation(async (url: string) => {
      if (url.endsWith("/ai/os/conversations")) return { data: { conversations: [{ id: 7, title: "Saved branch comparison", updated_at: "2026-09-25T10:00:00Z" }] } } as never;
      if (url.endsWith("/ai/os/conversations/7")) return { data: { id: 7, messages: [
        { id: 1, role: "user", content: "Compare my branches" }, { id: 2, role: "assistant", content: JSON.stringify(compare) },
        { id: 3, role: "user", content: "Help me reduce waste" }, { id: 4, role: "assistant", content: JSON.stringify({ ...chatReply, answer_text: "An older chat reply.", answer_type: "general_guidance" }) },
      ] } } as never;
      return { data: {} } as never;
    });
    render(<OsPage />);
    fireEvent.click(screen.getByRole("button", { name: "Previous conversations" }));
    fireEvent.click(await screen.findByRole("button", { name: /Saved branch comparison/ }));
    await screen.findByText(/Kasarani spends 37% of every sale/);
    expect(screen.getByText("An older chat reply.")).toBeTruthy();
  });

  it("a restaurant that records its own sales has no data-source banner; a mirrored one says what it is waiting for", async () => {
    render(<OsPage />);
    expect(screen.queryByText(/Restaurant data/)).toBeNull();
    expect(vi.mocked(api.get).mock.calls.some(([url]) => url.includes("/overview/today"))).toBe(false);
    cleanup();
    navigationState.tenant = "Vibanda Village";
    vi.mocked(api.get).mockImplementation(async (url: string) => (url.endsWith("/ai/os/conversations")
      ? { data: { conversations: [] } } : { data: { data_provenance: { source_connection: { state: "awaiting_first_delivery", reconciled: false } } } }) as never);
    render(<OsPage />);
    expect(await screen.findByText(/Restaurant data isn’t connected yet/)).toBeTruthy();
  });

  it("labels a creative answer as AI-written and names the modules it drew on", async () => {
    const creative = { ...chatReply, answer_type: "restaurant_analysis", llm_used: true, creative: true, consulted_modules: ["revenue", "menu", "staff"], llm_reply: "A warm, connected answer.", answer_text: "A warm, connected answer." };
    vi.mocked(api.post).mockImplementation(async (url: string) => (url.endsWith("/ai/os/conversations") ? { data: { id: 42 } } : { data: creative }) as never);
    render(<OsPage />);
    submit("Help me think about sales and dishes");
    await screen.findByText("A warm, connected answer.");
    expect(screen.getByText("Creative · AI-written · Restaurant analysis")).toBeTruthy();
    expect(screen.getByText("Drew on:").closest("p")!.textContent).toBe("Drew on:SalesMenuTeam");
  });

  it("says only AI-written when the layer is off, and adds no AI label when no model answered", async () => {
    const plain = { ...chatReply, answer_type: "general_guidance", llm_used: true, llm_reply: "Plain guidance.", answer_text: "Plain guidance." };
    vi.mocked(api.post).mockImplementation(async (url: string) => (url.endsWith("/ai/os/conversations") ? { data: { id: 42 } } : { data: plain }) as never);
    const first = render(<OsPage />);
    submit("Help me reduce food waste.");
    await screen.findByText("Plain guidance.");
    expect(screen.getByText("AI-written · General guidance from your description")).toBeTruthy();
    first.unmount();
    vi.mocked(api.post).mockImplementation(async (url: string) => (url.endsWith("/ai/os/conversations") ? { data: { id: 42 } } : { data: { ...plain, llm_used: false, llm_reply: null, answer_text: "Deterministic fallback text." } }) as never);
    render(<OsPage />);
    submit("Help me reduce food waste.");
    await screen.findByText("Deterministic fallback text.");
    expect(screen.getByText("General guidance from your description")).toBeTruthy();
    expect(screen.queryByText(/AI-written/)).toBeNull();
  });
});
