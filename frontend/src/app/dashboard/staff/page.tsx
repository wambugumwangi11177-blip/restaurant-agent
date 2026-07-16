"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { motion, AnimatePresence } from "framer-motion";
import { Users, Plus, X, Check, ShieldAlert } from "lucide-react";

const STAFF_ROLES = [
    { value: "manager", label: "Manager" },
    { value: "supervisor", label: "Supervisor" },
    { value: "controller", label: "Controller" },
    { value: "stockkeeper", label: "Stockkeeper" },
    { value: "kitchen", label: "Kitchen" },
    { value: "waiter", label: "Waiter" },
];

export default function StaffPage() {
    const [staff, setStaff] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [forbidden, setForbidden] = useState(false);
    const [showAddForm, setShowAddForm] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [toast, setToast] = useState("");

    const [name, setName] = useState("");
    const [roleTitle, setRoleTitle] = useState("");
    const [phone, setPhone] = useState("");
    const [hourlyRate, setHourlyRate] = useState("");
    const [createLogin, setCreateLogin] = useState(false);
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [staffRole, setStaffRole] = useState("waiter");

    const [assigningId, setAssigningId] = useState<number | null>(null);
    const [assignRole, setAssignRole] = useState("waiter");

    const showToast = (msg: string) => {
        setToast(msg);
        setTimeout(() => setToast(""), 3000);
    };

    const fetchStaff = async () => {
        try {
            const res = await api.get("/staff/");
            setStaff(Array.isArray(res.data) ? res.data : []);
            setForbidden(false);
        } catch (err: any) {
            if (err?.response?.status === 403) setForbidden(true);
        }
        setLoading(false);
    };

    useEffect(() => { fetchStaff(); }, []);

    const resetForm = () => {
        setName(""); setRoleTitle(""); setPhone(""); setHourlyRate("");
        setCreateLogin(false); setEmail(""); setPassword(""); setStaffRole("waiter");
    };

    const handleAdd = async () => {
        if (!name) return;
        setSubmitting(true);
        try {
            await api.post("/staff/", {
                name,
                role_title: roleTitle,
                phone: phone || null,
                hourly_rate: hourlyRate ? Math.round(parseFloat(hourlyRate) * 100) : 0,
                create_login: createLogin,
                email: createLogin ? email : null,
                password: createLogin ? password : null,
                staff_role: createLogin ? staffRole : null,
            });
            showToast(`Added ${name}`);
            setShowAddForm(false);
            resetForm();
            await fetchStaff();
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to add staff member");
        }
        setSubmitting(false);
    };

    const handleToggleActive = async (member: any) => {
        setSubmitting(true);
        try {
            await api.put(`/staff/${member.id}`, { is_active: !member.is_active });
            showToast(member.is_active ? `${member.name} deactivated — login revoked` : `${member.name} reactivated`);
            await fetchStaff();
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to update");
        }
        setSubmitting(false);
    };

    const handleAssignRole = async (memberId: number) => {
        setSubmitting(true);
        try {
            await api.post(`/staff/${memberId}/assign-role`, { staff_role: assignRole });
            showToast("Role updated");
            setAssigningId(null);
            await fetchStaff();
        } catch (err: any) {
            showToast(err?.response?.data?.detail || "Failed to assign role");
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

    if (forbidden) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[40vh] space-y-3 text-center">
                <ShieldAlert className="w-8 h-8 text-[#525252]" />
                <p className="text-sm text-[#737373]">
                    Staff management is only available to Owners and Managers.
                </p>
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

            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-xl font-bold text-[#e5e5e5]">Staff</h1>
                    <p className="text-sm text-[#525252] mt-0.5">
                        {staff.length} staff member{staff.length !== 1 ? "s" : ""} on the roster
                    </p>
                </div>
                <button onClick={() => setShowAddForm(!showAddForm)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--accent)]/10 border border-[var(--accent)]/30 rounded-lg text-xs text-[var(--accent)] hover:bg-[var(--accent)]/20 transition-all">
                    <Plus className="w-3 h-3" />
                    Add Staff
                </button>
            </div>

            <AnimatePresence>
                {showAddForm && (
                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                        className="bg-[#141414] border border-[var(--accent)]/20 rounded-xl overflow-hidden">
                        <div className="px-4 py-3 border-b border-[#1a1a1a] flex items-center justify-between">
                            <span className="text-xs font-semibold text-[#e5e5e5]">New Staff Member</span>
                            <button onClick={() => setShowAddForm(false)} aria-label="Close form"><X className="w-4 h-4 text-[#525252]" /></button>
                        </div>
                        <div className="p-4 space-y-3">
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                                <input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)}
                                    className="col-span-2 bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[var(--accent)]/50 focus:outline-none" />
                                <input placeholder="Job title (e.g. Head Chef)" value={roleTitle} onChange={(e) => setRoleTitle(e.target.value)}
                                    className="col-span-2 bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[var(--accent)]/50 focus:outline-none" />
                                <input placeholder="Phone (for WhatsApp/SMS)" value={phone} onChange={(e) => setPhone(e.target.value)}
                                    className="col-span-2 bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[var(--accent)]/50 focus:outline-none" />
                                <input placeholder="Hourly rate (KES)" value={hourlyRate} onChange={(e) => setHourlyRate(e.target.value)} type="number"
                                    className="col-span-2 bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[var(--accent)]/50 focus:outline-none" />
                            </div>

                            <label className="flex items-center gap-2 text-xs text-[#737373]">
                                <input type="checkbox" checked={createLogin} onChange={(e) => setCreateLogin(e.target.checked)} />
                                Give this person a dashboard login
                            </label>

                            {createLogin && (
                                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                                    <input placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)}
                                        className="col-span-2 bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[var(--accent)]/50 focus:outline-none" />
                                    <input placeholder="Temporary password" value={password} onChange={(e) => setPassword(e.target.value)} type="password"
                                        className="col-span-2 bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[var(--accent)]/50 focus:outline-none" />
                                    <select value={staffRole} onChange={(e) => setStaffRole(e.target.value)}
                                        className="col-span-2 bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] focus:border-[var(--accent)]/50 focus:outline-none">
                                        {STAFF_ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                                    </select>
                                </div>
                            )}

                            <button onClick={handleAdd} disabled={!name || submitting}
                                className="bg-[var(--accent)] text-black rounded-lg px-4 py-2 text-xs font-semibold disabled:opacity-50">
                                {submitting ? "Adding..." : "Add Staff Member"}
                            </button>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            <div className="bg-[#141414] border border-[#262626] rounded-xl">
                <div className="px-4 py-3 border-b border-[#1a1a1a] flex items-center gap-2">
                    <Users className="w-3.5 h-3.5 text-[var(--accent)]" />
                    <p className="text-xs font-semibold text-[#e5e5e5]">Roster</p>
                </div>
                <div className="divide-y divide-[#1a1a1a]">
                    {staff.length === 0 ? (
                        <p className="text-xs text-[#525252] text-center py-8">No staff on the roster yet</p>
                    ) : (
                        staff.map((member) => (
                            <div key={member.id} className="px-4 py-3">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-3 flex-1">
                                        <div className={`w-2 h-2 rounded-full flex-shrink-0 ${member.is_active ? "bg-[#22c55e]" : "bg-[#525252]"}`} />
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2">
                                                <p className="text-sm text-[#e5e5e5]">{member.name}</p>
                                                {member.staff_role ? (
                                                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-[var(--accent)]/10 text-[var(--accent)] uppercase">
                                                        {member.staff_role}
                                                    </span>
                                                ) : member.user_id ? (
                                                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#ef4444]/10 text-[#ef4444] uppercase">
                                                        role needed
                                                    </span>
                                                ) : null}
                                            </div>
                                            <p className="text-xs text-[#737373] mt-0.5">
                                                {member.role_title || "—"}{member.phone ? ` · ${member.phone}` : ""}
                                            </p>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-1">
                                        {member.user_id && (
                                            <button
                                                onClick={() => { setAssigningId(assigningId === member.id ? null : member.id); setAssignRole(member.staff_role || "waiter"); }}
                                                className="text-[10px] px-2 py-1 rounded bg-[#1a1a1a] text-[#737373] hover:text-[var(--accent)] transition-all">
                                                Set role
                                            </button>
                                        )}
                                        <button onClick={() => handleToggleActive(member)} disabled={submitting}
                                            className={`text-[10px] px-2 py-1 rounded transition-all ${member.is_active ? "bg-[#1a1a1a] text-[#737373] hover:text-[#ef4444]" : "bg-[#22c55e]/10 text-[#22c55e]"}`}>
                                            {member.is_active ? "Deactivate" : "Reactivate"}
                                        </button>
                                    </div>
                                </div>

                                <AnimatePresence>
                                    {assigningId === member.id && (
                                        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                            className="mt-2 flex gap-2 items-center">
                                            <select value={assignRole} onChange={(e) => setAssignRole(e.target.value)}
                                                className="flex-1 bg-[#1a1a1a] border border-[#262626] rounded-lg px-2 py-1.5 text-xs text-[#e5e5e5] focus:outline-none">
                                                {STAFF_ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                                            </select>
                                            <button onClick={() => handleAssignRole(member.id)} disabled={submitting}
                                                className="bg-[var(--accent)] text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
                                                {submitting ? "..." : "Save"}
                                            </button>
                                        </motion.div>
                                    )}
                                </AnimatePresence>
                            </div>
                        ))
                    )}
                </div>
            </div>
        </div>
    );
}
