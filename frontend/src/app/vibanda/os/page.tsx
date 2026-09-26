"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Check, ChevronDown, Clock3, Copy, Database, History, Search, Send, Sparkles, X } from "lucide-react";
import api from "@/lib/api";
import { VIBANDA_AREA_SECTIONS } from "@/lib/vibandaAreas";
import { OS_AREA_QUESTIONS, type OSQuestionPurpose } from "@/lib/osSuggestions";

type ChatResponse = {
  module: string;
  grounded?: { finding?: string; why?: string; recommendation?: string; data?: { evidence_note?: string } };
  llm_reply?: string | null;
  answer_text?: string | null;
  answer_type?: string;
  data_availability?: string;
  follow_up_prompts?: string[];
  proposal?: {
    title: string; request: string; expected_result: string; affected_page: string;
    layout: string; controls: string; mobile_behavior: string; can_apply: boolean;
  } | null;
  conversation_id?: number;
};
type ChatPurpose = OSQuestionPurpose | "auto";
type Turn = { id: string; question: string; purpose: ChatPurpose; topic?: string; answer?: ChatResponse; error?: boolean };
type SavedConversation = { id: number; title: string; updated_at: string };
type HandoffDraft = { title: string; text: string };
type SourceStatus = "checking" | "verified" | "awaiting" | "needs_reconciliation" | "unknown";

const STARTERS: { text: string; purpose: OSQuestionPurpose }[] = [
  { text: "Show me how this software can help my restaurant.", purpose: "capability" },
  { text: "Help me solve a problem.", purpose: "general" },
  { text: "I want to change something in my app.", purpose: "general" },
  { text: "Help me prepare for connecting my restaurant data.", purpose: "general" },
];

const AREA_BY_SLUG = new Map(OS_AREA_QUESTIONS.map((area) => [area.slug, area]));
const PURPOSE_MODE: Record<ChatPurpose, "auto" | "capabilities" | "general" | "analysis"> = {
  auto: "auto", capability: "capabilities", general: "general", analysis: "analysis",
};

function parseSavedTurns(messages: { id: number; role: string; content: string }[]): Turn[] {
  const result: Turn[] = [];
  for (let i = 0; i < messages.length; i += 1) {
    if (messages[i].role !== "user") continue;
    const assistant = messages[i + 1]?.role === "assistant" ? messages[i + 1] : undefined;
    let answer: ChatResponse | undefined;
    if (assistant) {
      try { answer = JSON.parse(assistant.content) as ChatResponse; } catch { answer = { module: "general", llm_reply: assistant.content }; }
    }
    result.push({ id: String(messages[i].id), question: messages[i].content, purpose: answer?.answer_type === "restaurant_analysis" ? "analysis" : answer?.answer_type === "capability_explanation" ? "capability" : "general", answer });
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

function redactCredentials(value: string): string {
  return cleanHandoffText(value);
}

function OSChatInner() {
  const params = useSearchParams();
  const [input, setInput] = useState("");
  const [search, setSearch] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [defaultArea, setDefaultArea] = useState<string | null>(null);
  const [preferencePreview, setPreferencePreview] = useState<{ before: string | null; after: string } | null>(null);
  const [preferenceSaved, setPreferenceSaved] = useState(false);
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
    api.get<{ data_provenance?: { source_connection?: { state?: string; reconciled?: boolean } } }>("/api/v1/overview/today", { timeout: 12000 })
      .then((response) => {
        const state = response.data?.data_provenance?.source_connection;
        if (active) setSourceStatus(state?.state === "receiving" ? state.reconciled === true ? "verified" : "needs_reconciliation" : state?.state === "awaiting_first_delivery" ? "awaiting" : "unknown");
      })
      .catch(() => { if (active) setSourceStatus("unknown"); });
    api.get<{ default_area: string | null }>("/api/v1/ai/os/preferences")
      .then((response) => { if (active) setDefaultArea(response.data.default_area); })
      .catch(() => undefined);
    void refreshHistory();
    return () => { active = false; };
  }, [refreshHistory]);

  const send = useCallback(async (question: string, purpose: ChatPurpose = "general", retryId?: string, topic?: string) => {
    const q = redactCredentials(question.trim());
    if (q.length < 3 || q.length > 500 || busyId) return;
    const id = retryId ?? crypto.randomUUID();
    const oldIndex = retryId ? turns.findIndex((turn) => turn.id === retryId) : -1;
    followReply.current = !chatViewport.current || chatViewport.current.scrollHeight - chatViewport.current.scrollTop - chatViewport.current.clientHeight < 96;
    setNewResponse(false);
    if (oldIndex >= 0) {
      setTurns((previous) => previous.map((turn) => turn.id === id ? { ...turn, error: false, answer: undefined } : turn));
    } else {
      setTurns((previous) => [...previous, { id, question: q, purpose, topic }]);
    }
    setBusyId(id);
    try {
      let activeConversation = conversationId;
      if (activeConversation == null) {
        const created = await api.post<{ id: number }>("/api/v1/ai/os/conversations", { title: q.slice(0, 120) });
        activeConversation = created.data.id;
        setConversationId(activeConversation);
      }
      const response = await api.post<ChatResponse>("/api/v1/ai/chat", {
        question: q,
        answer_mode: PURPOSE_MODE[purpose],
        topic,
        conversation_id: activeConversation,
        client_message_id: id,
      }, { timeout: 45000 });
      const answer = response.data;
      setConversationId(answer.conversation_id ?? activeConversation);
      setTurns((previous) => previous.map((turn) => turn.id === id ? { ...turn, answer, error: false } : turn));
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
    void send(question, "analysis");
  }, [params, send]);

  const filteredAreas = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const seenSearchQuestions = new Set<string>();
    return VIBANDA_AREA_SECTIONS.map((section) => ({
      ...section,
      areas: section.areas.map(([label, note, slug]) => ({
        label, note, slug, questions: (AREA_BY_SLUG.get(slug)?.questions ?? []).filter((question) => {
          if (needle && !label.toLowerCase().includes(needle) && !question.text.toLowerCase().includes(needle)) return false;
          if (needle && seenSearchQuestions.has(question.text)) return false;
          if (needle) seenSearchQuestions.add(question.text);
          return true;
        }),
      })).filter((area) => area.questions.length > 0),
    })).filter((section) => section.areas.length > 0);
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

  const applyDefault = async () => {
    if (!preferencePreview) return;
    const response = await api.put<{ default_area: string }>("/api/v1/ai/os/preferences", { default_area: preferencePreview.after });
    setDefaultArea(response.data.default_area);
    setPreferencePreview(null);
    setPreferenceSaved(true);
    window.setTimeout(() => setPreferenceSaved(false), 2600);
  };

  const prepareHandoff = (turn: Turn) => {
    const transcript = turns.slice(-8).map((item) => `Owner: ${item.question}\nOS: ${item.answer?.answer_text ?? item.answer?.llm_reply ?? item.answer?.grounded?.finding ?? "No verified answer returned."}`).join("\n\n");
    const text = cleanHandoffText([
      "Vibanda Restaurant OS — technical help request",
      `Owner goal: ${turn.question}`,
      `Page: ${window.location.origin}/vibanda/os`,
      `Restaurant: Vibanda Village`,
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

  const canBrowse = turns.length === 0;

  return (
    <div className="animate-rise-in space-y-6 pb-8">
      <header className="space-y-3">
        <div className="inline-flex items-center gap-2 rounded-full border border-[var(--v-border)] bg-[hsl(42_40%_99_/_0.65)] px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--v-muted-foreground)]">
          <Sparkles size={13} className="text-[var(--v-primary)]" /> Your operating partner
        </div>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="font-display text-[clamp(2rem,4vw,3.25rem)] font-semibold leading-tight tracking-[-0.045em]">What would you like to work on<span className="text-[var(--v-primary)]">?</span></h1>
            <p className="mt-2 max-w-2xl text-sm text-[var(--v-muted-foreground)]">Understand your restaurant tools, explore ideas, and plan your next change.</p>
          </div>
          <div className="flex gap-2">
            <button type="button" onClick={() => { setShowHistory(true); void refreshHistory(); }} className="inline-flex items-center gap-2 rounded-lg border border-[var(--v-border)] bg-[var(--v-card)] px-3 py-2 text-xs font-semibold hover:border-[var(--v-primary)]"><History size={14} /> Previous conversations</button>
            {turns.length > 0 && <button type="button" onClick={newConversation} className="rounded-lg border border-[var(--v-border)] px-3 py-2 text-xs font-semibold hover:bg-[var(--v-card)]">New conversation</button>}
          </div>
        </div>
      </header>

      <form onSubmit={(event) => { event.preventDefault(); void send(input, "auto"); }} className="sticky bottom-3 z-20 flex items-end gap-2 rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-2 shadow-[0_12px_40px_hsl(201_47%_29_/.10)] focus-within:border-[hsl(201_47%_29_/.65)]">
        <textarea value={input} maxLength={500} rows={input.includes("\n") ? 3 : 1} onChange={(event) => setInput(event.target.value)} aria-label="Ask or describe a change" placeholder="Ask a question or describe what you want to change…" className="max-h-32 min-h-11 min-w-0 flex-1 resize-y bg-transparent px-3 py-3 text-sm leading-relaxed outline-none placeholder:text-[hsl(207_12%_46_/.75)]" />
        <button type="submit" disabled={!!busyId || input.trim().length < 3} aria-label="Send question" className="mb-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[var(--v-primary)] text-[var(--v-primary-foreground)] disabled:opacity-50"><Send size={16} /></button>
      </form>

      {canBrowse ? <>
        <div className="flex items-start gap-2 rounded-lg bg-[hsl(42_40%_99_/_0.58)] px-3 py-2.5 text-xs text-[var(--v-muted-foreground)]">
          <Database size={14} className="mt-0.5 shrink-0 text-[var(--v-primary)]" />
          <span>{sourceStatus === "verified" ? "Verified restaurant data is connected. Ask the OS about the records it can verify." : sourceStatus === "checking" ? "Checking restaurant data status. You can still explore features and discuss ideas." : sourceStatus === "needs_reconciliation" ? "Restaurant data has arrived but isn’t reconciled yet. You can explore features and plan changes while findings wait for verification." : sourceStatus === "unknown" ? "Restaurant data status can’t be verified right now. You can still explore features, discuss ideas, and plan changes." : "Restaurant data isn’t connected yet. You can still explore features, discuss ideas, and prepare changes."}</span>
        </div>
        <section aria-label="Start a conversation" className="grid gap-2 sm:grid-cols-2">
          {STARTERS.map((starter) => <button type="button" key={starter.text} onClick={() => void send(starter.text, starter.purpose)} className="group flex min-h-16 items-center justify-between gap-3 rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-4 text-left text-sm font-medium transition hover:-translate-y-0.5 hover:border-[var(--v-primary)]/50 hover:shadow-sm">
            <span>{starter.text}</span><span className="text-lg text-[var(--v-primary)] transition-transform group-hover:translate-x-1">→</span>
          </button>)}
        </section>
        <section className="space-y-3" aria-label="Explore by business area">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div><p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[var(--v-muted-foreground)]">Explore by business area</p><h2 className="font-display mt-1 text-xl font-semibold">Find a useful place to start</h2></div>
            <label className="flex items-center gap-2 rounded-lg border border-[var(--v-border)] bg-[var(--v-card)] px-3 py-2"><Search size={14} className="text-[var(--v-muted-foreground)]" /><input value={search} onChange={(event) => setSearch(event.target.value)} aria-label="Search all OS questions" placeholder="Search questions" className="w-44 bg-transparent text-xs outline-none" /></label>
          </div>
          {filteredAreas.map((section) => <details key={section.id} open={defaultArea === section.id || !!search} className="group rounded-xl border border-[var(--v-border)] bg-[var(--v-card)]">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 p-4"><span><span className="block text-sm font-semibold">{section.title}</span><span className="mt-1 block text-xs text-[var(--v-muted-foreground)]">{section.areas.length} areas to explore</span></span><ChevronDown size={16} className="shrink-0 text-[var(--v-muted-foreground)] transition-transform group-open:rotate-180" /></summary>
            <div className="space-y-3 border-t border-[var(--v-border)] px-3 py-3 sm:px-4">
              {section.areas.map((area) => <div key={area.slug} className="rounded-lg bg-[hsl(42_40%_99_/_0.56)] p-3">
                <div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="text-sm font-semibold">{area.label}</h3><p className="mt-0.5 text-xs text-[var(--v-muted-foreground)]">{area.note}</p></div><button type="button" onClick={() => { setPreferencePreview({ before: defaultArea, after: section.id }); setPreferenceSaved(false); }} className="rounded-md px-2 py-1 text-[10px] font-semibold text-[var(--v-primary)] hover:bg-[var(--v-muted)]">{defaultArea === section.id ? "Your default area" : "Make my default"}</button></div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {area.questions.filter((question) => question.purpose !== "analysis" || search).slice(0, search ? area.questions.length : 2).map((question) => <button type="button" key={`${area.slug}-${question.text}`} onClick={() => void send(question.text, question.purpose, undefined, area.slug)} className="rounded-lg border border-[var(--v-border)] bg-white/70 px-3 py-2 text-left text-xs transition hover:border-[var(--v-primary)]/50"><span>{question.text}</span>{question.needsConnectedData && <span className="ml-2 text-[10px] text-[var(--v-muted-foreground)]">Needs connected data</span>}{question.availability === "planned" && <span className="ml-2 text-[10px] text-[var(--v-muted-foreground)]">Planned feature</span>}</button>)}
                </div>
                {!search && area.questions.some((question) => question.purpose === "analysis") && <details className="mt-2 rounded-lg border border-dashed border-[var(--v-border)]"><summary className="cursor-pointer px-3 py-2 text-[11px] font-semibold text-[var(--v-muted-foreground)]">Questions that need connected data <span className="font-normal">({area.questions.filter((question) => question.purpose === "analysis").length})</span></summary><div className="flex flex-wrap gap-2 px-3 pb-3">{area.questions.filter((question) => question.purpose === "analysis").map((question) => <button type="button" key={`${area.slug}-${question.text}`} onClick={() => void send(question.text, question.purpose, undefined, area.slug)} className="rounded-lg border border-[var(--v-border)] bg-white/70 px-3 py-2 text-left text-xs hover:border-[var(--v-primary)]/50"><span>{question.text}</span><span className="mt-1 block text-[10px] text-[var(--v-muted-foreground)]">Needs connected data{question.availability === "planned" ? " · Planned feature" : ""}</span></button>)}</div></details>}
              </div>)}
            </div>
          </details>)}
        </section>
      </> : <>
        <div className="flex items-center justify-between gap-3"><p className="text-xs text-[var(--v-muted-foreground)]">Conversation saved privately to your Vibanda owner account.</p><button type="button" onClick={() => { setSearch(""); document.getElementById("browse-questions")?.scrollIntoView({ block: "nearest" }); }} className="text-xs font-semibold text-[var(--v-primary)]">Browse questions</button></div>
        {sourceStatus !== "verified" && <p className="flex items-center gap-2 rounded-lg bg-[hsl(42_40%_99_/_0.58)] px-3 py-2 text-[11px] text-[var(--v-muted-foreground)]"><Database size={13} />{sourceStatus === "needs_reconciliation" ? "Restaurant records need source reconciliation before the OS can treat findings as verified." : sourceStatus === "unknown" ? "The restaurant data status could not be verified; feature explanations and general guidance remain available." : "Restaurant data isn’t connected yet; feature explanations and general guidance remain available."}</p>}
        <div ref={chatViewport} aria-live="polite" className="max-h-[62vh] space-y-4 overflow-y-auto rounded-xl border border-[var(--v-border)] bg-[hsl(42_40%_99_/_0.34)] p-3 sm:p-5">
          {turns.map((turn) => <article key={turn.id} className="space-y-3">
            <div className="ml-auto max-w-[92%] sm:max-w-[78%]"><p className="mb-1 text-right text-[10px] font-semibold text-[var(--v-muted-foreground)]">Your question</p><div className="rounded-2xl rounded-br-sm bg-[var(--v-primary)] px-4 py-3 text-sm leading-relaxed text-[var(--v-primary-foreground)]">{turn.question}</div></div>
            <div className="max-w-[96%] rounded-2xl rounded-bl-sm border border-[var(--v-border)] bg-[var(--v-card)] p-4 shadow-sm sm:max-w-[88%]">
                {turn.error ? <div role="alert" className="space-y-2"><p className="text-sm">I couldn’t reach the answer service. Your message is still here so you can retry it.</p><button type="button" onClick={() => void send(turn.question, turn.purpose, turn.id, turn.topic)} className="rounded-lg border border-[var(--v-border)] px-3 py-1.5 text-xs font-semibold">Retry answer</button></div> : turn.answer ? <div className="space-y-3">
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--v-muted-foreground)]">{turn.answer.answer_type === "capability_explanation" ? "Software explanation" : turn.answer.answer_type === "planned_feature" ? "Planned feature" : turn.answer.answer_type === "general_guidance" ? "General guidance from your description" : turn.answer.data_availability === "available" ? "Verified restaurant analysis" : turn.answer.data_availability === "needs_source_verification" ? "Records need source verification" : "Data needed before analysis"}</p>
                <p className="whitespace-pre-wrap text-sm leading-relaxed">{turn.answer.answer_text || turn.answer.llm_reply || turn.answer.grounded?.finding || "I can help explain the software or plan a next step."}</p>
                {turn.answer.answer_type === "restaurant_analysis" && turn.answer.data_availability === "needs_connected_data" && <p className="rounded-lg bg-[hsl(42_40%_99_/_0.8)] px-3 py-2 text-xs text-[var(--v-muted-foreground)]">This question needs connected restaurant records. No restaurant result has been inferred.</p>}
                {turn.answer.answer_type === "restaurant_analysis" && turn.answer.data_availability === "needs_source_verification" && <p className="rounded-lg bg-[hsl(42_40%_99_/_0.8)] px-3 py-2 text-xs text-[var(--v-muted-foreground)]">Records exist, but the source has not passed a clean reconciliation. No restaurant result is treated as verified.</p>}
                {turn.answer.data_availability === "planned_feature" && <p className="rounded-lg bg-[hsl(42_40%_99_/_0.8)] px-3 py-2 text-xs text-[var(--v-muted-foreground)]">This owner area is planned. Connecting restaurant data alone will not enable this analysis.</p>}
                {turn.answer.answer_type === "restaurant_analysis" && turn.answer.grounded?.why && <details className="text-xs text-[var(--v-muted-foreground)]"><summary className="cursor-pointer font-semibold">Evidence and limits</summary><p className="mt-2">{turn.answer.grounded.why}</p>{turn.answer.grounded.data?.evidence_note && <p className="mt-1">{turn.answer.grounded.data.evidence_note}</p>}</details>}
                {turn.answer.follow_up_prompts?.length ? <div className="flex flex-wrap gap-2">{turn.answer.follow_up_prompts.map((prompt) => <button key={prompt} type="button" onClick={() => void send(prompt, "general")} className="rounded-full border border-[var(--v-border)] px-3 py-1.5 text-[11px] hover:border-[var(--v-primary)]">{prompt}</button>)}</div> : null}
                {turn.answer.proposal && <div className="space-y-2 rounded-xl border border-[hsl(43_76%_57_/.55)] bg-[hsl(42_71%_75_/.16)] p-3 text-xs"><div className="flex items-center justify-between gap-2"><p className="font-bold">{turn.answer.proposal.title}</p><span className="rounded-full bg-white/70 px-2 py-1 text-[10px] font-semibold">Proposal — not applied</span></div><p><strong>Request:</strong> {turn.answer.proposal.request}</p><p><strong>Expected result:</strong> {turn.answer.proposal.expected_result}</p><p><strong>Page:</strong> {turn.answer.proposal.affected_page}</p><details><summary className="cursor-pointer font-semibold">Design notes</summary><div className="mt-2 space-y-1"><p>{turn.answer.proposal.layout}</p><p>{turn.answer.proposal.controls}</p><p>Mobile: {turn.answer.proposal.mobile_behavior}</p></div></details></div>}
                {(turn.answer.proposal || turn.answer.answer_type === "planned_feature") && <button type="button" onClick={() => prepareHandoff(turn)} className="text-[11px] font-semibold text-[var(--v-primary)]">Prepare summary for technical help</button>}
              </div> : <div role="status" className="flex items-center gap-2 text-sm text-[var(--v-muted-foreground)]"><span className="h-2 w-2 animate-pulse rounded-full bg-[var(--v-primary)]" />Working on your question…</div>}
            </div>
          </article>)}
          <div aria-hidden="true" />
        </div>
        {busyId && <p role="status" className="text-center text-[11px] text-[var(--v-muted-foreground)]">Preparing a grounded answer…</p>}
        {newResponse && <button type="button" onClick={() => { chatViewport.current?.scrollTo({ top: chatViewport.current.scrollHeight, behavior: "smooth" }); setNewResponse(false); }} className="mx-auto block rounded-full border border-[var(--v-border)] bg-[var(--v-card)] px-4 py-2 text-xs font-semibold shadow-sm">New response ↓</button>}
        <div id="browse-questions" className="space-y-3">
          <div className="flex items-center justify-between gap-3"><h2 className="font-display text-lg font-semibold">Browse questions</h2><label className="flex items-center gap-2 rounded-lg border border-[var(--v-border)] bg-[var(--v-card)] px-3 py-2"><Search size={14} /><input value={search} onChange={(event) => setSearch(event.target.value)} aria-label="Search all OS questions" placeholder="Search questions" className="w-36 bg-transparent text-xs outline-none" /></label></div>
          {filteredAreas.map((section) => <details key={section.id} open={!!search} className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)]"><summary className="cursor-pointer px-4 py-3 text-sm font-semibold">{section.title}</summary><div className="space-y-3 border-t border-[var(--v-border)] p-3">{section.areas.map((area) => <div key={area.slug}><p className="mb-1 text-xs font-semibold">{area.label}</p><div className="flex flex-wrap gap-2">{area.questions.map((question) => <button type="button" key={`${area.slug}-${question.text}`} onClick={() => void send(question.text, question.purpose, undefined, area.slug)} className="rounded-lg border border-[var(--v-border)] px-3 py-2 text-left text-xs hover:border-[var(--v-primary)]"><span>{question.text}</span>{question.needsConnectedData && <span className="ml-2 text-[10px] text-[var(--v-muted-foreground)]">Needs connected data</span>}{question.availability === "planned" && <span className="ml-2 text-[10px] text-[var(--v-muted-foreground)]">Planned feature</span>}</button>)}</div></div>)}</div></details>)}
        </div>
      </>}

      {preferencePreview && <div role="dialog" aria-label="Preview default OS area" className="fixed inset-x-4 bottom-20 z-30 mx-auto max-w-md rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-4 shadow-xl"><div className="flex items-start justify-between gap-3"><div><p className="text-sm font-semibold">Preview your OS starting area</p><p className="mt-2 text-xs text-[var(--v-muted-foreground)]">Before: {VIBANDA_AREA_SECTIONS.find((section) => section.id === preferencePreview.before)?.title ?? "No default"}</p><p className="mt-1 text-xs text-[var(--v-muted-foreground)]">After: {VIBANDA_AREA_SECTIONS.find((section) => section.id === preferencePreview.after)?.title}</p></div><button type="button" onClick={() => setPreferencePreview(null)} aria-label="Close preview"><X size={16} /></button></div><div className="mt-3 flex justify-end gap-2"><button type="button" onClick={() => setPreferencePreview(null)} className="rounded-lg px-3 py-2 text-xs">Cancel</button><button type="button" onClick={() => void applyDefault()} className="rounded-lg bg-[var(--v-primary)] px-3 py-2 text-xs font-semibold text-[var(--v-primary-foreground)]">Apply preference</button></div></div>}
      {preferenceSaved && <p role="status" className="text-center text-xs font-semibold text-[var(--v-primary)]"><Check size={14} className="mr-1 inline" />Your default area is saved.</p>}
      {handoff && <div role="dialog" aria-modal="true" aria-label={handoff.title} className="fixed inset-0 z-40 flex items-end justify-center bg-black/35 p-3 sm:items-center"><div className="w-full max-w-xl space-y-3 rounded-2xl border border-[var(--v-border)] bg-[var(--v-card)] p-4 shadow-2xl sm:p-5"><div className="flex items-center justify-between"><h2 className="font-display text-lg font-semibold">{handoff.title}</h2><button type="button" onClick={() => setHandoff(null)} aria-label="Close technical help summary"><X size={18} /></button></div><p className="text-xs text-[var(--v-muted-foreground)]">Review the text, then copy it to share by WhatsApp or discuss by phone. Nothing is sent automatically.</p><textarea readOnly value={handoff.text} rows={10} className="w-full resize-y rounded-lg border border-[var(--v-border)] bg-white/70 p-3 text-xs leading-relaxed" /><button type="button" onClick={() => void copyHandoff()} className="inline-flex items-center gap-2 rounded-lg bg-[var(--v-primary)] px-4 py-2.5 text-xs font-semibold text-[var(--v-primary-foreground)]"><Copy size={14} />{copied ? "Copied" : "Copy summary"}</button></div></div>}
      {showHistory && <div role="dialog" aria-modal="true" aria-label="Previous conversations" className="fixed inset-0 z-40 flex items-end justify-center bg-black/35 p-3 sm:items-center"><div className="w-full max-w-lg rounded-2xl border border-[var(--v-border)] bg-[var(--v-card)] p-4 shadow-2xl"><div className="mb-3 flex items-center justify-between"><h2 className="font-display text-lg font-semibold">Previous conversations</h2><button type="button" onClick={() => setShowHistory(false)} aria-label="Close conversation history"><X size={18} /></button></div><div className="max-h-[55vh] space-y-2 overflow-y-auto">{historyBusy ? <p className="p-4 text-sm text-[var(--v-muted-foreground)]">Loading saved conversations…</p> : conversations.length === 0 ? <p className="p-4 text-sm text-[var(--v-muted-foreground)]">Your saved conversations will appear here.</p> : conversations.map((item) => <button type="button" key={item.id} onClick={() => void loadConversation(item)} className="flex w-full items-center gap-3 rounded-lg border border-[var(--v-border)] p-3 text-left hover:border-[var(--v-primary)]"><Clock3 size={15} className="shrink-0 text-[var(--v-primary)]" /><span className="min-w-0 flex-1 truncate text-sm">{item.title}</span><span className="text-[10px] text-[var(--v-muted-foreground)]">{new Date(item.updated_at).toLocaleDateString()}</span></button>)}</div></div></div>}
    </div>
  );
}

export default function VibandaOsPage() {
  return <Suspense fallback={<div role="status" className="p-6 text-sm text-[var(--v-muted-foreground)]">Loading the Vibanda OS…</div>}><OSChatInner /></Suspense>;
}
