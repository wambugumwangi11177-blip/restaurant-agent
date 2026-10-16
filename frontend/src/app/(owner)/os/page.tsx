"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ChevronDown, Clock3, Copy, Database, History, Search, Send, Sparkles, X } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import AnswerCard from "@/components/owner/ask/AnswerCard";
import { tenantConfig } from "@/lib/tenantConfig";
import { ASK_FORMS, asOwnerAnswer, isGuidance, type AskForm, type OwnerAnswer } from "@/lib/owner/ask";

/** An explanation of the software or help with an idea: the writing assistant answers these (/ai/chat). Everything about the owner's own figures is answered in the five forms (/owner/ask). */
type ChatResponse = {
  module: string;
  grounded?: { finding?: string; why?: string; recommendation?: string; data?: { evidence_note?: string } };
  llm_reply?: string | null;
  answer_text?: string | null;
  answer_type?: string;
  llm_used?: boolean;
  creative?: boolean;
  consulted_modules?: string[];
  follow_up_prompts?: string[];
  proposal?: {
    title: string; request: string; expected_result: string; affected_page: string;
    layout: string; controls: string; mobile_behavior: string; can_apply: boolean;
  } | null;
  conversation_id?: number;
};
type Chat = "capabilities" | "general" | "auto";
/** How a question is sent: to the five forms (optionally one the owner picked), or to the writing assistant. */
type Route = { chat: Chat } | { form: AskForm | "auto" };
type Turn = { id: string; question: string; route: Route; chat?: ChatResponse; owner?: OwnerAnswer; error?: boolean };
type SavedConversation = { id: number; title: string; updated_at: string };
type HandoffDraft = { title: string; text: string };
type SourceStatus = "checking" | "verified" | "awaiting" | "needs_reconciliation" | "unknown";

const STARTERS: { text: string; chat: Chat }[] = [
  { text: "Show me how this software can help my restaurant.", chat: "capabilities" },
  { text: "Help me solve a problem.", chat: "general" },
  { text: "I want to change something in my app.", chat: "general" },
  { text: "Help me prepare for connecting my restaurant data.", chat: "general" },
];

// Backend module ids -> the words the owner uses for those areas.
const MODULE_LABEL: Record<string, string> = {
  stock: "Stock", revenue: "Sales", bookings: "Bookings", kitchen: "Kitchen", staff: "Team",
  menu: "Menu", pricing: "Pricing", profit: "Profit", ops: "Operations",
};

function parseSavedTurns(messages: { id: number; role: string; content: string }[]): Turn[] {
  const result: Turn[] = [];
  for (let i = 0; i < messages.length; i += 1) {
    if (messages[i].role !== "user") continue;
    const assistant = messages[i + 1]?.role === "assistant" ? messages[i + 1] : undefined;
    let owner: OwnerAnswer | undefined;
    let chat: ChatResponse | undefined;
    if (assistant) {
      try {
        const parsed: unknown = JSON.parse(assistant.content);
        owner = asOwnerAnswer(parsed) ?? undefined;
        if (!owner) chat = parsed as ChatResponse;
      } catch { chat = { module: "general", llm_reply: assistant.content }; }
    }
    result.push({ id: String(messages[i].id), question: messages[i].content, route: owner ? { form: owner.form } : { chat: "auto" }, chat, owner });
  }
  return result;
}

function cleanHandoffText(value: string): string {
  return value
    .replace(/(password|passcode|api[_ -]?key|access[_ -]?token|client[_ -]?secret|secret|credential)\s*[:=]\s*(?:"[^"]*"|'[^']*'|[^\s,;]+)/gi, "$1: [removed]")
    .replace(/\bBearer\s+[A-Za-z0-9._~+/=-]+/gi, "Bearer [removed]")
    .replace(/-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g, "[private key removed]")
    .replace(/\bpostgres(?:ql)?:\/\/[^\s]+/gi, "[database connection string removed]")
    .slice(0, 9000);
}

function OSChatInner() {
  const params = useSearchParams();
  const { user } = useAuth();
  const restaurantName = user?.restaurant_name || "my restaurant";
  const macsoft = tenantConfig(user?.tenant_name).source === "macsoft";
  const [input, setInput] = useState("");
  const [form, setForm] = useState<AskForm | "auto">("auto");
  const [search, setSearch] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<SavedConversation[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [sourceStatus, setSourceStatus] = useState<SourceStatus>("checking");
  const [handoff, setHandoff] = useState<HandoffDraft | null>(null);
  const [copied, setCopied] = useState(false);
  const [newResponse, setNewResponse] = useState(false);
  const chatViewport = useRef<HTMLDivElement>(null);
  const followReply = useRef(true);
  const autoAsked = useRef(false);

  const refreshHistory = useCallback(async () => {
    try {
      const response = await api.get<{ conversations: SavedConversation[] }>("/api/v1/ai/os/conversations");
      setConversations(response.data.conversations ?? []);
    } catch { /* History stays optional if its service is temporarily unavailable. */ }
  }, []);

  useEffect(() => {
    let active = true;
    // Only a restaurant whose figures are a mirror of its till (Macsoft) has anything to wait for.
    if (macsoft) {
      api.get<{ data_provenance?: { source_connection?: { state?: string; reconciled?: boolean } } }>("/api/v1/overview/today", { timeout: 12000 })
        .then((response) => {
          const state = response.data?.data_provenance?.source_connection;
          if (active) setSourceStatus(state?.state === "receiving" ? state.reconciled === true ? "verified" : "needs_reconciliation" : state?.state === "awaiting_first_delivery" ? "awaiting" : "unknown");
        })
        .catch(() => { if (active) setSourceStatus("unknown"); });
    } else {
      setSourceStatus("verified");
    }
    void refreshHistory();
    return () => { active = false; };
  }, [refreshHistory, macsoft]);

  const send = useCallback(async (question: string, route: Route, retryId?: string) => {
    const q = cleanHandoffText(question.trim());
    if (q.length < 3 || q.length > 500 || busyId) return;
    // Typed words about the owner's own figures go to the five forms; a request for help or an explanation goes to the writing assistant.
    const resolved: Route = "form" in route && route.form === "auto" && isGuidance(q) ? { chat: "auto" } : route;
    const id = retryId ?? crypto.randomUUID();
    const oldIndex = retryId ? turns.findIndex((turn) => turn.id === retryId) : -1;
    followReply.current = !chatViewport.current || chatViewport.current.scrollHeight - chatViewport.current.scrollTop - chatViewport.current.clientHeight < 96;
    setNewResponse(false);
    if (oldIndex >= 0) {
      setTurns((previous) => previous.map((turn) => turn.id === id ? { ...turn, error: false, chat: undefined, owner: undefined } : turn));
    } else {
      setTurns((previous) => [...previous, { id, question: q, route: resolved }]);
    }
    setBusyId(id);
    try {
      let activeConversation = conversationId;
      if (activeConversation == null) {
        const created = await api.post<{ id: number }>("/api/v1/ai/os/conversations", { title: q.slice(0, 120) });
        activeConversation = created.data.id;
        setConversationId(activeConversation);
      }
      if ("chat" in resolved) {
        const response = await api.post<ChatResponse>("/api/v1/ai/chat", {
          question: q, answer_mode: resolved.chat, conversation_id: activeConversation, client_message_id: id,
        }, { timeout: 45000 });
        setConversationId(response.data.conversation_id ?? activeConversation);
        setTurns((previous) => previous.map((turn) => turn.id === id ? { ...turn, chat: response.data, error: false } : turn));
      } else {
        const response = await api.post<OwnerAnswer>("/api/v1/owner/ask", {
          question: q, ...(resolved.form !== "auto" ? { form: resolved.form } : {}), conversation_id: activeConversation, client_message_id: id,
        }, { timeout: 45000 });
        setConversationId(response.data.conversation_id ?? activeConversation);
        setTurns((previous) => previous.map((turn) => turn.id === id ? { ...turn, owner: response.data, error: false } : turn));
      }
      setInput("");
      void refreshHistory();
      if (followReply.current) requestAnimationFrame(() => {
        if (chatViewport.current) chatViewport.current.scrollTop = chatViewport.current.scrollHeight;
      });
      else setNewResponse(true);
    } catch {
      setTurns((previous) => previous.map((turn) => turn.id === id ? { ...turn, error: true } : turn));
      setInput(q);
    } finally {
      setBusyId(null);
    }
  }, [busyId, conversationId, refreshHistory, turns]);

  useEffect(() => {
    const question = params.get("q");
    if (!question || autoAsked.current) return;
    autoAsked.current = true;
    void send(question, { form: "auto" });
  }, [params, send]);

  const groups = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return ASK_FORMS.map((f) => ({ ...f, examples: f.examples.filter((text) => !needle || text.toLowerCase().includes(needle) || f.label.toLowerCase().includes(needle)) }))
      .filter((f) => f.examples.length > 0);
  }, [search]);

  const newConversation = () => {
    setConversationId(null);
    setTurns([]);
    setHandoff(null);
    setNewResponse(false);
    setShowHistory(false);
  };

  const loadConversation = async (item: SavedConversation) => {
    setHistoryBusy(true);
    try {
      const response = await api.get<{ id: number; messages: { id: number; role: string; content: string }[] }>(`/api/v1/ai/os/conversations/${item.id}`);
      setConversationId(response.data.id);
      setTurns(parseSavedTurns(response.data.messages));
      setShowHistory(false);
      setHandoff(null);
      setNewResponse(false);
    } finally { setHistoryBusy(false); }
  };

  const prepareHandoff = (turn: Turn) => {
    const transcript = turns.slice(-8).map((item) => `Owner: ${item.question}\nOS: ${item.owner?.headline ?? item.chat?.answer_text ?? item.chat?.llm_reply ?? item.chat?.grounded?.finding ?? "No verified answer returned."}`).join("\n\n");
    const text = cleanHandoffText([
      "Restaurant OS — technical help request",
      `Owner goal: ${turn.question}`,
      `Page: ${window.location.origin}/os`,
      `Restaurant: ${restaurantName}`,
      "Conversation context (recent messages):",
      transcript,
      "Requested next step: review this request with the owner by WhatsApp or phone.",
    ].join("\n\n"));
    setHandoff({ title: "Review this summary before sharing", text });
    setCopied(false);
  };

  const copyHandoff = async () => {
    if (!handoff) return;
    await navigator.clipboard.writeText(handoff.text);
    setCopied(true);
  };

  const ask = (question: string, f?: AskForm) => void send(question, { form: f ?? "auto" });
  const canBrowse = turns.length === 0;
  const questionBrowser = (open: boolean) => (
    <section className="space-y-3" aria-label="Questions to try">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div><p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--v-muted-foreground)]">Questions to try</p><h2 className="font-display mt-1 text-xl font-semibold">Ask in five ways</h2></div>
        <label className="flex items-center gap-2 rounded-lg border border-[var(--v-border)] bg-[var(--v-card)] px-3 py-2"><Search size={14} className="text-[var(--v-muted-foreground)]" /><input value={search} onChange={(event) => setSearch(event.target.value)} aria-label="Search all OS questions" placeholder="Search questions" className="w-44 bg-transparent text-xs outline-none" /></label>
      </div>
      {groups.map((group) => <details key={group.id} open={open || !!search} className="group rounded-xl border border-[var(--v-border)] bg-[var(--v-card)]">
        <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-4 p-4"><span><span className="block text-sm font-semibold">{group.label}</span><span className="mt-1 block text-xs text-[var(--v-muted-foreground)]">{group.hint}</span></span><ChevronDown size={16} className="shrink-0 text-[var(--v-muted-foreground)] transition-transform group-open:rotate-180" /></summary>
        <div className="flex flex-wrap gap-2 border-t border-[var(--v-border)] px-3 py-3 sm:px-4">
          {group.examples.map((text) => <button type="button" key={text} onClick={() => void send(text, { form: group.id })} className="min-h-10 rounded-lg border border-[var(--v-border)] bg-white/70 px-3 py-2 text-left text-xs transition hover:border-[var(--v-primary)]/50">{text}</button>)}
        </div>
      </details>)}
    </section>
  );

  return (
    <div className="animate-rise-in space-y-6 pb-8">
      <header className="space-y-3">
        <div className="inline-flex items-center gap-2 rounded-full border border-[var(--v-border)] bg-[hsl(42_40%_99_/_0.65)] px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">
          <Sparkles size={13} className="text-[var(--v-primary)]" /> Your operating partner
        </div>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="font-display text-[clamp(2rem,4vw,3.25rem)] font-semibold leading-tight tracking-[-0.045em]">What would you like to work on<span className="text-[var(--v-primary)]">?</span></h1>
            <p className="mt-2 max-w-2xl text-sm text-[var(--v-muted-foreground)]">Ask what is happening, why, what if, what to do, or compare. Every number comes from your own records.</p>
          </div>
          <div className="flex gap-2">
            <button type="button" onClick={() => { setShowHistory(true); void refreshHistory(); }} className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-[var(--v-border)] bg-[var(--v-card)] px-3 py-2 text-xs font-semibold hover:border-[var(--v-primary)]"><History size={14} /> Previous conversations</button>
            {turns.length > 0 && <button type="button" onClick={newConversation} className="min-h-10 rounded-lg border border-[var(--v-border)] px-3 py-2 text-xs font-semibold hover:bg-[var(--v-card)]">New conversation</button>}
          </div>
        </div>
      </header>

      <form onSubmit={(event) => { event.preventDefault(); void send(input, { form }); }} className="sticky bottom-3 z-20 space-y-2 rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-2 shadow-[0_12px_40px_hsl(201_47%_29%_/.10)] focus-within:border-[hsl(201_47%_29%_/.65)]">
        <div className="flex items-end gap-2">
          <textarea value={input} maxLength={500} rows={input.includes("\n") ? 3 : 1} onChange={(event) => setInput(event.target.value)} aria-label="Ask or describe a change" placeholder="Ask a question about your restaurant…" className="max-h-32 min-h-11 min-w-0 flex-1 resize-y bg-transparent px-3 py-3 text-sm leading-relaxed outline-none placeholder:text-[hsl(207_12%_46_/.75)]" />
          <button type="submit" disabled={!!busyId || input.trim().length < 3} aria-label="Send question" className="mb-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[var(--v-primary)] text-[var(--v-primary-foreground)] disabled:opacity-50"><Send size={16} /></button>
        </div>
        <div role="radiogroup" aria-label="Answer as" className="flex flex-wrap gap-1.5 px-1 pb-1">
          {[{ id: "auto" as const, label: "Let LEVIII choose" }, ...ASK_FORMS].map((f) => (
            <button key={f.id} type="button" role="radio" aria-checked={form === f.id} onClick={() => setForm(f.id)}
              className={`min-h-10 rounded-full border px-3 text-[11px] font-semibold ${form === f.id ? "border-[var(--v-primary)] bg-[hsl(201_47%_29%_/_0.1)] text-[var(--v-primary)]" : "border-[var(--v-border)] text-[var(--v-muted-foreground)]"}`}>{f.label}</button>
          ))}
        </div>
      </form>

      {canBrowse ? <>
        {macsoft && <div className="flex items-start gap-2 rounded-lg bg-[hsl(42_40%_99_/_0.58)] px-3 py-2.5 text-xs text-[var(--v-muted-foreground)]">
          <Database size={14} className="mt-0.5 shrink-0 text-[var(--v-primary)]" />
          <span>{sourceStatus === "verified" ? "Verified restaurant data is connected. Ask about the records it can verify." : sourceStatus === "checking" ? "Checking restaurant data status. You can still explore features and discuss ideas." : sourceStatus === "needs_reconciliation" ? "Restaurant data has arrived but isn’t reconciled yet. You can explore features and plan changes while findings wait for verification." : sourceStatus === "unknown" ? "Restaurant data status can’t be verified right now. You can still explore features, discuss ideas, and plan changes." : "Restaurant data isn’t connected yet. You can still explore features, discuss ideas, and prepare changes."}</span>
        </div>}
        {questionBrowser(false)}
        <section aria-label="Start a conversation" className="space-y-2">
          <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--v-muted-foreground)]">Or talk it through</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {STARTERS.map((starter) => <button type="button" key={starter.text} onClick={() => void send(starter.text, { chat: starter.chat })} className="group flex min-h-16 items-center justify-between gap-3 rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-4 text-left text-sm font-medium transition hover:-translate-y-0.5 hover:border-[var(--v-primary)]/50 hover:shadow-sm">
              <span>{starter.text}</span><span className="text-lg text-[var(--v-primary)] transition-transform group-hover:translate-x-1">→</span>
            </button>)}
          </div>
        </section>
      </> : <>
        <p className="text-xs text-[var(--v-muted-foreground)]">Conversation saved privately to your owner account.</p>
        <div ref={chatViewport} role="region" aria-label="Conversation messages" aria-live="polite" onScroll={(event) => {
          const viewport = event.currentTarget;
          followReply.current = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < 96;
          if (followReply.current) setNewResponse(false);
        }} className="max-h-[62vh] space-y-4 overflow-y-auto rounded-xl border border-[var(--v-border)] bg-[hsl(42_40%_99_/_0.34)] p-3 sm:p-5">
          {turns.map((turn) => <article key={turn.id} className="space-y-3">
            <div className="ml-auto max-w-[92%] sm:max-w-[78%]"><p className="mb-1 text-right text-[10px] font-semibold text-[var(--v-muted-foreground)]">Your question</p><div className="rounded-2xl rounded-br-sm bg-[var(--v-primary)] px-4 py-3 text-sm leading-relaxed text-[var(--v-primary-foreground)]">{turn.question}</div></div>
            <div className="max-w-[96%] rounded-2xl rounded-bl-sm border border-[var(--v-border)] bg-[var(--v-card)] p-4 shadow-sm sm:max-w-[88%]">
              {turn.error ? <div role="alert" className="space-y-2"><p className="text-sm">I couldn’t reach the answer service. Your message is still here so you can retry it.</p><button type="button" onClick={() => void send(turn.question, turn.route, turn.id)} className="min-h-10 rounded-lg border border-[var(--v-border)] px-3 py-1.5 text-xs font-semibold">Retry answer</button></div>
                : turn.owner ? <AnswerCard answer={turn.owner} onAsk={ask} />
                : turn.chat ? <div className="space-y-3">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--v-muted-foreground)]">{turn.chat.creative ? "Creative · AI-written · " : turn.chat.llm_used ? "AI-written · " : ""}{turn.chat.answer_type === "capability_explanation" ? "Software explanation" : turn.chat.answer_type === "general_guidance" ? "General guidance from your description" : "Restaurant analysis"}</p>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">{turn.chat.answer_text || turn.chat.llm_reply || turn.chat.grounded?.finding || "I can help explain the software or plan a next step."}</p>
                  {turn.chat.consulted_modules?.length ? <p className="flex flex-wrap items-center gap-1.5 text-[10px] text-[var(--v-muted-foreground)]"><span>Drew on:</span>{turn.chat.consulted_modules.map((id) => <span key={id} className="rounded-full border border-[var(--v-border)] px-2 py-0.5 font-semibold">{MODULE_LABEL[id] ?? id}</span>)}</p> : null}
                  {turn.chat.follow_up_prompts?.length ? <div className="flex flex-wrap gap-2">{turn.chat.follow_up_prompts.map((prompt) => <button key={prompt} type="button" onClick={() => void send(prompt, { chat: "general" })} className="min-h-10 rounded-full border border-[var(--v-border)] px-3 py-1.5 text-[11px] hover:border-[var(--v-primary)]">{prompt}</button>)}</div> : null}
                  {turn.chat.proposal && <div className="space-y-2 rounded-xl border border-[hsl(43_76%_57_/.55)] bg-[hsl(42_71%_75_/.16)] p-3 text-xs"><div className="flex items-center justify-between gap-2"><p className="font-bold">{turn.chat.proposal.title}</p><span className="rounded-full bg-white/70 px-2 py-1 text-[10px] font-semibold">Proposal — not applied</span></div><p><strong>Request:</strong> {turn.chat.proposal.request}</p><p><strong>Expected result:</strong> {turn.chat.proposal.expected_result}</p><p><strong>Page:</strong> {turn.chat.proposal.affected_page}</p><details><summary className="cursor-pointer font-semibold">Design notes</summary><div className="mt-2 space-y-1"><p>{turn.chat.proposal.layout}</p><p>{turn.chat.proposal.controls}</p><p>Mobile: {turn.chat.proposal.mobile_behavior}</p></div></details></div>}
                  {turn.chat.proposal && <button type="button" onClick={() => prepareHandoff(turn)} className="min-h-10 text-[11px] font-semibold text-[var(--v-primary)]">Prepare summary for technical help</button>}
                </div> : <div role="status" className="flex items-center gap-2 text-sm text-[var(--v-muted-foreground)]"><span className="h-2 w-2 animate-pulse rounded-full bg-[var(--v-primary)]" />Working on your question…</div>}
            </div>
          </article>)}
          <div aria-hidden="true" />
        </div>
        {busyId && <p role="status" className="text-center text-[11px] text-[var(--v-muted-foreground)]">Working it out from your records…</p>}
        {newResponse && <button type="button" onClick={() => { chatViewport.current?.scrollTo({ top: chatViewport.current.scrollHeight, behavior: "smooth" }); setNewResponse(false); }} className="mx-auto block min-h-10 rounded-full border border-[var(--v-border)] bg-[var(--v-card)] px-4 py-2 text-xs font-semibold shadow-sm">New response ↓</button>}
        <div id="browse-questions">{questionBrowser(false)}</div>
      </>}

      {handoff && <div role="dialog" aria-modal="true" aria-label={handoff.title} className="fixed inset-0 z-40 flex items-end justify-center bg-black/35 p-3 sm:items-center"><div className="w-full max-w-xl space-y-3 rounded-2xl border border-[var(--v-border)] bg-[var(--v-card)] p-4 shadow-2xl sm:p-5"><div className="flex items-center justify-between"><h2 className="font-display text-lg font-semibold">{handoff.title}</h2><button type="button" onClick={() => setHandoff(null)} aria-label="Close technical help summary" className="flex h-10 w-10 items-center justify-center"><X size={18} /></button></div><p className="text-xs text-[var(--v-muted-foreground)]">Review the text, then copy it to share by WhatsApp or discuss by phone. Nothing is sent automatically.</p><textarea readOnly value={handoff.text} rows={10} className="w-full resize-y rounded-lg border border-[var(--v-border)] bg-white/70 p-3 text-xs leading-relaxed" /><button type="button" onClick={() => void copyHandoff()} className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-[var(--v-primary)] px-4 py-2.5 text-xs font-semibold text-[var(--v-primary-foreground)]"><Copy size={14} />{copied ? "Copied" : "Copy summary"}</button></div></div>}
      {showHistory && <div role="dialog" aria-modal="true" aria-label="Previous conversations" className="fixed inset-0 z-40 flex items-end justify-center bg-black/35 p-3 sm:items-center"><div className="w-full max-w-lg rounded-2xl border border-[var(--v-border)] bg-[var(--v-card)] p-4 shadow-2xl"><div className="mb-3 flex items-center justify-between"><h2 className="font-display text-lg font-semibold">Previous conversations</h2><button type="button" onClick={() => setShowHistory(false)} aria-label="Close conversation history" className="flex h-10 w-10 items-center justify-center"><X size={18} /></button></div><div className="max-h-[55vh] space-y-2 overflow-y-auto">{historyBusy ? <p className="p-4 text-sm text-[var(--v-muted-foreground)]">Loading saved conversations…</p> : conversations.length === 0 ? <p className="p-4 text-sm text-[var(--v-muted-foreground)]">Your saved conversations will appear here.</p> : conversations.map((item) => <button type="button" key={item.id} onClick={() => void loadConversation(item)} className="flex min-h-12 w-full items-center gap-3 rounded-lg border border-[var(--v-border)] p-3 text-left hover:border-[var(--v-primary)]"><Clock3 size={15} className="shrink-0 text-[var(--v-primary)]" /><span className="min-w-0 flex-1 truncate text-sm">{item.title}</span><span className="text-[10px] text-[var(--v-muted-foreground)]">{new Date(item.updated_at).toLocaleDateString()}</span></button>)}</div></div></div>}
    </div>
  );
}

export default function OsPage() {
  return <Suspense fallback={<div role="status" className="p-6 text-sm text-[var(--v-muted-foreground)]">Loading Ask LEVIII…</div>}><OSChatInner /></Suspense>;
}
