"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { motion, AnimatePresence } from "framer-motion";
import { LifeBuoy, Plus, X, ChevronLeft, Send } from "lucide-react";
import { useToast } from "@/components/ui/Toast";
import FormField from "@/components/ui/FormField";
import { getErrorMessage } from "@/lib/errors";

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
    open: "bg-warning/10 text-warning border-warning/30",
    in_progress: "bg-info/10 text-info border-info/30",
    resolved: "bg-success/10 text-success border-success/30",
    closed: "bg-border text-text-muted border-[#333]",
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
    const isTriage = user?.role === "admin" || user?.role === "superadmin" || user?.staff_role === "manager";

    const [tickets, setTickets] = useState<TicketSummary[]>([]);
    const [loading, setLoading] = useState(true);
    const { showToast, toastNode } = useToast();

    const [showNewForm, setShowNewForm] = useState(false);
    const [subject, setSubject] = useState("");
    const [message, setMessage] = useState("");
    const [submitting, setSubmitting] = useState(false);

    const [selected, setSelected] = useState<TicketDetail | null>(null);
    const [reply, setReply] = useState("");

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
        } catch (err) {
            showToast(getErrorMessage(err, "Couldn't open ticket"), "error");
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
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to create ticket"), "error");
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
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to send reply"), "error");
        }
        setSubmitting(false);
    };

    const handleStatusChange = async (status: string) => {
        if (!selected) return;
        setSubmitting(true);
        try {
            await api.post(`/support/tickets/${selected.id}/status`, { status });
            await openTicket(selected.id);
            await fetchTickets();
            showToast(`Marked ${statusLabel(status)}`);
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to update status"), "error");
        }
        setSubmitting(false);
    };

    if (loading) {
        return (
            <div className="space-y-3">
                {[...Array(3)].map((_, i) => (
                    <div key={i} className="bg-surface rounded-xl h-14 animate-pulse" />
                ))}
            </div>
        );
    }

    return (
        <div className="space-y-5">
            {toastNode}

            {selected ? (
                <div className="space-y-4">
                    <button onClick={() => setSelected(null)}
                        className="flex items-center gap-1 text-xs text-text-muted hover:text-text">
                        <ChevronLeft className="w-3.5 h-3.5" /> Back to tickets
                    </button>

                    <div className="flex items-start justify-between gap-3">
                        <div>
                            <h1 className="text-lg font-bold text-text">{selected.subject}</h1>
                            <span className={`inline-block mt-1 text-[10px] px-2 py-0.5 rounded-full border ${STATUS_STYLES[selected.status] || ""}`}>
                                {statusLabel(selected.status)}
                            </span>
                        </div>
                        {isTriage && (
                            <div className="flex flex-col gap-1">
                                <label htmlFor="ticket-status" className="sr-only">Ticket status</label>
                                <select
                                    id="ticket-status"
                                    value={selected.status}
                                    onChange={(e) => handleStatusChange(e.target.value)}
                                    disabled={submitting}
                                    className="bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text focus:border-accent/50 focus:outline-none"
                                >
                                    {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}
                                </select>
                            </div>
                        )}
                    </div>

                    <div className="bg-surface border border-surface-hover rounded-xl divide-y divide-surface-hover">
                        {selected.messages.map((m) => (
                            <div key={m.id} className="px-4 py-3">
                                <div className="flex items-center justify-between mb-1">
                                    <span className="text-xs font-medium text-text">{m.sender_email}</span>
                                    <span className="text-[10px] text-text-dim">
                                        {new Date(m.created_at).toLocaleString()}
                                    </span>
                                </div>
                                <p className="text-xs text-[#a3a3a3] whitespace-pre-wrap">{m.body}</p>
                            </div>
                        ))}
                    </div>

                    <div className="flex gap-2 items-end">
                        <FormField
                            label="Reply"
                            srOnlyLabel
                            value={reply}
                            onChange={(e) => setReply(e.target.value)}
                            onKeyDown={(e) => { if (e.key === "Enter") handleReply(); }}
                            placeholder="Write a reply..."
                            className="flex-1 bg-surface-hover border border-border rounded-lg px-3 py-2 text-xs text-text placeholder-text-dim focus:border-accent/50 focus:outline-none"
                        />
                        <button
                            onClick={handleReply}
                            disabled={submitting || !reply.trim()}
                            className="flex items-center gap-1.5 px-3 py-2 bg-accent/10 border border-accent/30 rounded-lg text-xs text-accent hover:bg-accent/20 transition-all disabled:opacity-40"
                        >
                            <Send className="w-3 h-3" /> Send
                        </button>
                    </div>
                </div>
            ) : (
                <>
                    <div className="flex items-center justify-between">
                        <div>
                            <h1 className="text-xl font-bold text-text">Support</h1>
                            <p className="text-sm text-text-dim mt-0.5">
                                {isTriage
                                    ? `${tickets.length} ticket${tickets.length !== 1 ? "s" : ""} across the team`
                                    : `${tickets.length} of your ticket${tickets.length !== 1 ? "s" : ""}`}
                            </p>
                        </div>
                        <button onClick={() => setShowNewForm(!showNewForm)}
                            className="flex items-center gap-1.5 px-3 py-1.5 bg-accent/10 border border-accent/30 rounded-lg text-xs text-accent hover:bg-accent/20 transition-all">
                            <Plus className="w-3 h-3" /> New Ticket
                        </button>
                    </div>

                    <AnimatePresence>
                        {showNewForm && (
                            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                className="bg-surface border border-accent/20 rounded-xl overflow-hidden">
                                <div className="px-4 py-3 border-b border-surface-hover flex items-center justify-between">
                                    <span className="text-xs font-semibold text-text">New Support Ticket</span>
                                    <button onClick={() => setShowNewForm(false)} aria-label="Close form"><X className="w-4 h-4 text-text-dim" /></button>
                                </div>
                                <div className="p-4 space-y-3">
                                    <FormField
                                        label="Subject"
                                        placeholder="What's the issue?" value={subject} onChange={(e) => setSubject(e.target.value)}
                                        className="w-full bg-surface-hover border border-border rounded-lg px-3 py-2 text-xs text-text placeholder-text-dim focus:border-accent/50 focus:outline-none" />
                                    <div className="flex flex-col gap-1">
                                        <label htmlFor="ticket-description" className="text-xs text-text-muted">Description</label>
                                        <textarea id="ticket-description" placeholder="Describe what's happening..." value={message} onChange={(e) => setMessage(e.target.value)} rows={3}
                                            className="w-full bg-surface-hover border border-border rounded-lg px-3 py-2 text-xs text-text placeholder-text-dim focus:border-accent/50 focus:outline-none resize-none" />
                                    </div>
                                    <button onClick={handleCreate} disabled={submitting || !subject.trim() || !message.trim()}
                                        className="px-4 py-2 bg-accent/10 border border-accent/30 rounded-lg text-xs text-accent hover:bg-accent/20 transition-all disabled:opacity-40">
                                        Submit
                                    </button>
                                </div>
                            </motion.div>
                        )}
                    </AnimatePresence>

                    {tickets.length === 0 ? (
                        <div className="flex flex-col items-center justify-center min-h-[30vh] space-y-3 text-center">
                            <LifeBuoy className="w-8 h-8 text-text-dim" />
                            <p className="text-sm text-text-muted">No support tickets yet.</p>
                        </div>
                    ) : (
                        <div className="bg-surface border border-surface-hover rounded-xl divide-y divide-surface-hover">
                            {tickets.map((t) => (
                                <button
                                    key={t.id}
                                    onClick={() => openTicket(t.id)}
                                    className="w-full text-left px-4 py-3 hover:bg-[#151515] transition-colors flex items-center justify-between gap-3"
                                >
                                    <div className="min-w-0">
                                        <p className="text-sm text-text truncate">{t.subject}</p>
                                        <p className="text-[11px] text-text-dim mt-0.5">
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
