"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { motion, AnimatePresence } from "framer-motion";
import { LifeBuoy, Plus, X, Check, ChevronLeft, Send } from "lucide-react";

interface TicketSummary {
    id: number;
    subject: string;
    status: string;
    created_by_id: number;
    created_by_email: string;
    created_at: string;
    updated_at: string;
    message_count: number;
    last_message_at: string | null;
}

interface TicketMessage {
    id: number;
    sender_id: number;
    sender_email: string;
    body: string;
    created_at: string;
}

interface TicketDetail {
    id: number;
    subject: string;
    status: string;
    created_by_id: number;
    created_at: string;
    updated_at: string;
    messages: TicketMessage[];
}

const STATUS_STYLES: Record<string, string> = {
    open: "bg-amber-500/10 text-amber-400 border-amber-500/30",
    in_progress: "bg-blue-500/10 text-blue-400 border-blue-500/30",
    resolved: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
    closed: "bg-[#262626] text-[#737373] border-[#333]",
};

const STATUS_OPTIONS = ["open", "in_progress", "resolved", "closed"];

function statusLabel(s: string) {
    return s.replace("_", " ");
}

/**
 * In-app support ticketing UI, shared by the Owner dashboard
 * (/dashboard/support) and every staff tier (/staff/<tier>/support). Any
 * authenticated user can raise/view their own tickets; Owner (admin) and
 * Manager-tier users triage the whole roster (backend enforces this — see
 * routers/support.py's _is_triage). Extracted from the original
 * dashboard/support/page.tsx unchanged so both surfaces stay in lockstep.
 */
export default function SupportView() {
    const { user } = useAuth();
    const isTriage = user?.role === "admin" || user?.role === "superadmin" || (user as any)?.staff_role === "manager";

    const [tickets, setTickets] = useState<TicketSummary[]>([]);
    const [loading, setLoading] = useState(true);
    const [toast, setToast] = useState("");

    const [showNewForm, setShowNewForm] = useState(false);
    const [subject, setSubject] = useState("");
    const [message, setMessage] = useState("");
    const [submitting, setSubmitting] = useState(false);

    const [selected, setSelected] = useState<TicketDetail | null>(null);
    const [reply, setReply] = useState("");

    const showToast = (msg: string) => {
        setToast(msg);
        setTimeout(() => setToast(""), 3000);
    };

    const fetchTickets = async () => {
        try {
            const res = await api.get("/support/tickets");
            setTickets(Array.isArray(res.data) ? res.data : []);
        } catch {
            // Leave the previous list in place rather than clearing on a
            // transient failure.
        }
        setLoading(false);
    };

    useEffect(() => { fetchTickets(); }, []);

    const openTicket = async (id: number) => {
        try {
            const res = await api.get(`/support/tickets/${id}`);
            setSelected(res.data);
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Couldn't open ticket");
        }
    };

    const handleCreate = async () => {
        if (!subject.trim() || !message.trim()) return;
        setSubmitting(true);
        try {
            await api.post("/support/tickets", { subject, message });
            showToast("Ticket created");
            setSubject(""); setMessage(""); setShowNewForm(false);
            await fetchTickets();
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to create ticket");
        }
        setSubmitting(false);
    };

    const handleReply = async () => {
        if (!selected || !reply.trim()) return;
        setSubmitting(true);
        try {
            const res = await api.post(`/support/tickets/${selected.id}/messages`, { body: reply });
            setSelected(res.data);
            setReply("");
            await fetchTickets();
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to send reply");
        }
        setSubmitting(false);
    };

    const handleStatusChange = async (status: string) => {
        if (!selected) return;
        setSubmitting(true);
        try {
            await api.patch(`/support/tickets/${selected.id}/status`, { status });
            await openTicket(selected.id);
            await fetchTickets();
            showToast(`Marked ${statusLabel(status)}`);
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to update status");
        }
        setSubmitting(false);
    };

    if (loading) {
        return (
            <div className="space-y-3">
                {[...Array(3)].map((_, i) => (
                    <div key={i} className="bg-[#141414] rounded-xl h-14 animate-pulse" />
                ))}
            </div>
        );
    }

    return (
        <div className="space-y-5">
            <AnimatePresence>
                {toast && (
                    <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}
                        className="fixed top-4 right-4 z-50 bg-[#22c55e]/10 border border-[#22c55e]/30 rounded-xl px-5 py-3 flex items-center gap-2">
                        <Check className="w-4 h-4 text-[#22c55e]" />
                        <span className="text-sm text-[#22c55e]">{toast}</span>
                    </motion.div>
                )}
            </AnimatePresence>

            {selected ? (
                <div className="space-y-4">
                    <button onClick={() => setSelected(null)}
                        className="flex items-center gap-1 text-xs text-[#737373] hover:text-[#e5e5e5]">
                        <ChevronLeft className="w-3.5 h-3.5" /> Back to tickets
                    </button>

                    <div className="flex items-start justify-between gap-3">
                        <div>
                            <h1 className="text-lg font-bold text-[#e5e5e5]">{selected.subject}</h1>
                            <span className={`inline-block mt-1 text-[10px] px-2 py-0.5 rounded-full border ${STATUS_STYLES[selected.status] || ""}`}>
                                {statusLabel(selected.status)}
                            </span>
                        </div>
                        {isTriage && (
                            <select
                                value={selected.status}
                                onChange={(e) => handleStatusChange(e.target.value)}
                                disabled={submitting}
                                className="bg-[#1a1a1a] border border-[#262626] rounded-lg px-2 py-1.5 text-xs text-[#e5e5e5] focus:border-[var(--accent)]/50 focus:outline-none"
                            >
                                {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}
                            </select>
                        )}
                    </div>

                    <div className="bg-[#141414] border border-[#1a1a1a] rounded-xl divide-y divide-[#1a1a1a]">
                        {selected.messages.map((m) => (
                            <div key={m.id} className="px-4 py-3">
                                <div className="flex items-center justify-between mb-1">
                                    <span className="text-xs font-medium text-[#e5e5e5]">{m.sender_email}</span>
                                    <span className="text-[10px] text-[#525252]">
                                        {new Date(m.created_at).toLocaleString()}
                                    </span>
                                </div>
                                <p className="text-xs text-[#a3a3a3] whitespace-pre-wrap">{m.body}</p>
                            </div>
                        ))}
                    </div>

                    <div className="flex gap-2">
                        <input
                            value={reply}
                            onChange={(e) => setReply(e.target.value)}
                            onKeyDown={(e) => { if (e.key === "Enter") handleReply(); }}
                            placeholder="Write a reply..."
                            className="flex-1 bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[var(--accent)]/50 focus:outline-none"
                        />
                        <button
                            onClick={handleReply}
                            disabled={submitting || !reply.trim()}
                            className="flex items-center gap-1.5 px-3 py-2 bg-[var(--accent)]/10 border border-[var(--accent)]/30 rounded-lg text-xs text-[var(--accent)] hover:bg-[var(--accent)]/20 transition-all disabled:opacity-40"
                        >
                            <Send className="w-3 h-3" /> Send
                        </button>
                    </div>
                </div>
            ) : (
                <>
                    <div className="flex items-center justify-between">
                        <div>
                            <h1 className="text-xl font-bold text-[#e5e5e5]">Support</h1>
                            <p className="text-sm text-[#525252] mt-0.5">
                                {isTriage
                                    ? `${tickets.length} ticket${tickets.length !== 1 ? "s" : ""} across the team`
                                    : `${tickets.length} of your ticket${tickets.length !== 1 ? "s" : ""}`}
                            </p>
                        </div>
                        <button onClick={() => setShowNewForm(!showNewForm)}
                            className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--accent)]/10 border border-[var(--accent)]/30 rounded-lg text-xs text-[var(--accent)] hover:bg-[var(--accent)]/20 transition-all">
                            <Plus className="w-3 h-3" /> New Ticket
                        </button>
                    </div>

                    <AnimatePresence>
                        {showNewForm && (
                            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                className="bg-[#141414] border border-[var(--accent)]/20 rounded-xl overflow-hidden">
                                <div className="px-4 py-3 border-b border-[#1a1a1a] flex items-center justify-between">
                                    <span className="text-xs font-semibold text-[#e5e5e5]">New Support Ticket</span>
                                    <button onClick={() => setShowNewForm(false)} aria-label="Close form"><X className="w-4 h-4 text-[#525252]" /></button>
                                </div>
                                <div className="p-4 space-y-3">
                                    <input placeholder="What's the issue?" value={subject} onChange={(e) => setSubject(e.target.value)}
                                        className="w-full bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[var(--accent)]/50 focus:outline-none" />
                                    <textarea placeholder="Describe what's happening..." value={message} onChange={(e) => setMessage(e.target.value)} rows={3}
                                        className="w-full bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[var(--accent)]/50 focus:outline-none resize-none" />
                                    <button onClick={handleCreate} disabled={submitting || !subject.trim() || !message.trim()}
                                        className="px-4 py-2 bg-[var(--accent)]/10 border border-[var(--accent)]/30 rounded-lg text-xs text-[var(--accent)] hover:bg-[var(--accent)]/20 transition-all disabled:opacity-40">
                                        Submit
                                    </button>
                                </div>
                            </motion.div>
                        )}
                    </AnimatePresence>

                    {tickets.length === 0 ? (
                        <div className="flex flex-col items-center justify-center min-h-[30vh] space-y-3 text-center">
                            <LifeBuoy className="w-8 h-8 text-[#525252]" />
                            <p className="text-sm text-[#737373]">No support tickets yet.</p>
                        </div>
                    ) : (
                        <div className="bg-[#141414] border border-[#1a1a1a] rounded-xl divide-y divide-[#1a1a1a]">
                            {tickets.map((t) => (
                                <button
                                    key={t.id}
                                    onClick={() => openTicket(t.id)}
                                    className="w-full text-left px-4 py-3 hover:bg-[#151515] transition-colors flex items-center justify-between gap-3"
                                >
                                    <div className="min-w-0">
                                        <p className="text-sm text-[#e5e5e5] truncate">{t.subject}</p>
                                        <p className="text-[11px] text-[#525252] mt-0.5">
                                            {isTriage ? `${t.created_by_email} · ` : ""}
                                            {t.message_count} message{t.message_count !== 1 ? "s" : ""}
                                        </p>
                                    </div>
                                    <span className={`shrink-0 text-[10px] px-2 py-0.5 rounded-full border ${STATUS_STYLES[t.status] || ""}`}>
                                        {statusLabel(t.status)}
                                    </span>
                                </button>
                            ))}
                        </div>
                    )}
                </>
            )}
        </div>
    );
}
