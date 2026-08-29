"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { tierHome, type StaffTier } from "@/lib/permissions";
import { motion, AnimatePresence } from "framer-motion";
import { Users, Plus, X, ShieldAlert, Eye } from "lucide-react";
import { useToast } from "@/components/ui/Toast";
import FormField from "@/components/ui/FormField";
import { getErrorMessage, isHttpStatus } from "@/lib/errors";

interface StaffMember {
    id: number;
    name: string;
    role_title: string | null;
    phone: string | null;
    is_active: boolean;
    user_id: number | null;
    staff_role: string | null;
}

const STAFF_ROLES = [
    { value: "manager", label: "Manager" },
    { value: "supervisor", label: "Supervisor" },
    { value: "controller", label: "Controller" },
    { value: "stockkeeper", label: "Stockkeeper" },
    { value: "kitchen", label: "Kitchen" },
    { value: "waiter", label: "Waiter" },
];

export default function StaffPage() {
    const { user, startImpersonation } = useAuth();
    const router = useRouter();
    // /staff/{id}/impersonate is require_role(ADMIN) server-side — an Owner
    // capability, not part of the 7-tier matrix. A Manager can also reach
    // this page (directive 015: `staff` = RW for Manager too), so the button
    // must not render for them — it would always 403 with a confusing error.
    const canImpersonate = ["admin", "superadmin"].includes((user?.role || "").toLowerCase());
    const [staff, setStaff] = useState<StaffMember[]>([]);
    const [loading, setLoading] = useState(true);
    const [forbidden, setForbidden] = useState(false);
    const [showAddForm, setShowAddForm] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [impersonatingId, setImpersonatingId] = useState<number | null>(null);
    const { showToast, toastNode } = useToast();

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

    const fetchStaff = async () => {
        try {
            const res = await api.get("/staff/");
            setStaff(Array.isArray(res.data) ? res.data : []);
            setForbidden(false);
        } catch (err) {
            if (isHttpStatus(err, 403)) setForbidden(true);
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
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to add staff member"), "error");
        }
        setSubmitting(false);
    };

    const handleToggleActive = async (member: StaffMember) => {
        setSubmitting(true);
        try {
            await api.put(`/staff/${member.id}`, { is_active: !member.is_active });
            showToast(member.is_active ? `${member.name} deactivated — login revoked` : `${member.name} reactivated`);
            await fetchStaff();
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to update"), "error");
        }
        setSubmitting(false);
    };

    const handleViewAs = async (member: StaffMember) => {
        setImpersonatingId(member.id);
        try {
            await startImpersonation(member.id);
            router.push(tierHome(member.staff_role as StaffTier | null));
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to start impersonation"), "error");
            setImpersonatingId(null);
        }
    };

    const handleAssignRole = async (memberId: number) => {
        setSubmitting(true);
        try {
            await api.post(`/staff/${memberId}/assign-role`, { staff_role: assignRole });
            showToast("Role updated");
            setAssigningId(null);
            await fetchStaff();
        } catch (err) {
            showToast(getErrorMessage(err, "Failed to assign role"), "error");
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

    if (forbidden) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[40vh] space-y-3 text-center">
                <ShieldAlert className="w-8 h-8 text-text-dim" />
                <p className="text-sm text-text-muted">
                    Staff management is only available to Owners and Managers.
                </p>
            </div>
        );
    }

    return (
        <div className="space-y-5">
            {toastNode}

            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-xl font-bold text-text">Staff</h1>
                    <p className="text-sm text-text-dim mt-0.5">
                        {staff.length} staff member{staff.length !== 1 ? "s" : ""} on the roster
                    </p>
                </div>
                <button onClick={() => setShowAddForm(!showAddForm)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-accent/10 border border-accent/30 rounded-lg text-xs text-accent hover:bg-accent/20 transition-all">
                    <Plus className="w-3 h-3" />
                    Add Staff
                </button>
            </div>

            <AnimatePresence>
                {showAddForm && (
                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                        className="bg-surface border border-accent/20 rounded-xl overflow-hidden">
                        <div className="px-4 py-3 border-b border-surface-hover flex items-center justify-between">
                            <span className="text-xs font-semibold text-text">New Staff Member</span>
                            <button onClick={() => setShowAddForm(false)} aria-label="Close form"><X className="w-4 h-4 text-text-dim" /></button>
                        </div>
                        <div className="p-4 space-y-3">
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                                <FormField
                                    label="Name"
                                    placeholder="Name" value={name} onChange={(e) => setName(e.target.value)}
                                    className="col-span-2 bg-surface-hover border border-border rounded-lg px-3 py-2 text-xs text-text placeholder-text-dim focus:border-accent/50 focus:outline-none w-full" />
                                <FormField
                                    label="Job title"
                                    placeholder="Job title (e.g. Head Chef)" value={roleTitle} onChange={(e) => setRoleTitle(e.target.value)}
                                    className="col-span-2 bg-surface-hover border border-border rounded-lg px-3 py-2 text-xs text-text placeholder-text-dim focus:border-accent/50 focus:outline-none w-full" />
                                <FormField
                                    label="Phone"
                                    placeholder="Phone (for WhatsApp/SMS)" value={phone} onChange={(e) => setPhone(e.target.value)}
                                    className="col-span-2 bg-surface-hover border border-border rounded-lg px-3 py-2 text-xs text-text placeholder-text-dim focus:border-accent/50 focus:outline-none w-full" />
                                <FormField
                                    label="Hourly rate (KES)"
                                    placeholder="Hourly rate (KES)" value={hourlyRate} onChange={(e) => setHourlyRate(e.target.value)} type="number"
                                    className="col-span-2 bg-surface-hover border border-border rounded-lg px-3 py-2 text-xs text-text placeholder-text-dim focus:border-accent/50 focus:outline-none w-full" />
                            </div>

                            <label className="flex items-center gap-2 text-xs text-text-muted">
                                <input type="checkbox" checked={createLogin} onChange={(e) => setCreateLogin(e.target.checked)} />
                                Give this person a dashboard login
                            </label>

                            {createLogin && (
                                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                                    <FormField
                                        label="Email"
                                        placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)}
                                        className="col-span-2 bg-surface-hover border border-border rounded-lg px-3 py-2 text-xs text-text placeholder-text-dim focus:border-accent/50 focus:outline-none w-full" />
                                    <FormField
                                        label="Temporary password"
                                        placeholder="Temporary password" value={password} onChange={(e) => setPassword(e.target.value)} type="password"
                                        className="col-span-2 bg-surface-hover border border-border rounded-lg px-3 py-2 text-xs text-text placeholder-text-dim focus:border-accent/50 focus:outline-none w-full" />
                                    <div className="col-span-2 flex flex-col gap-1">
                                        <label htmlFor="new-staff-role" className="text-xs text-text-muted">Dashboard role</label>
                                        <select id="new-staff-role" value={staffRole} onChange={(e) => setStaffRole(e.target.value)}
                                            className="bg-surface-hover border border-border rounded-lg px-3 py-2 text-xs text-text focus:border-accent/50 focus:outline-none">
                                            {STAFF_ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                                        </select>
                                    </div>
                                </div>
                            )}

                            <button onClick={handleAdd} disabled={!name || submitting}
                                className="bg-accent text-black rounded-lg px-4 py-2 text-xs font-semibold disabled:opacity-50">
                                {submitting ? "Adding..." : "Add Staff Member"}
                            </button>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            <div className="bg-surface border border-border rounded-xl">
                <div className="px-4 py-3 border-b border-surface-hover flex items-center gap-2">
                    <Users className="w-3.5 h-3.5 text-accent" />
                    <p className="text-xs font-semibold text-text">Roster</p>
                </div>
                <div className="divide-y divide-surface-hover">
                    {staff.length === 0 ? (
                        <p className="text-xs text-text-dim text-center py-8">No staff on the roster yet</p>
                    ) : (
                        staff.map((member) => (
                            <div key={member.id} className="px-4 py-3">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-3 flex-1">
                                        <div className={`w-2 h-2 rounded-full flex-shrink-0 ${member.is_active ? "bg-success" : "bg-text-dim"}`} />
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2">
                                                <p className="text-sm text-text">{member.name}</p>
                                                {member.staff_role ? (
                                                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-accent/10 text-accent uppercase">
                                                        {member.staff_role}
                                                    </span>
                                                ) : member.user_id ? (
                                                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-danger/10 text-danger uppercase">
                                                        role needed
                                                    </span>
                                                ) : null}
                                            </div>
                                            <p className="text-xs text-text-muted mt-0.5">
                                                {member.role_title || "—"}{member.phone ? ` · ${member.phone}` : ""}
                                            </p>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-1">
                                        {canImpersonate && member.user_id && member.staff_role && member.is_active && (
                                            <button
                                                onClick={() => handleViewAs(member)}
                                                disabled={impersonatingId === member.id}
                                                title="Sign in as this staff member (real session, audit-logged, ends automatically)"
                                                className="flex items-center gap-1 text-[10px] px-2 py-1 rounded bg-surface-hover text-text-muted hover:text-amber-400 transition-all disabled:opacity-50">
                                                <Eye className="w-3 h-3" />
                                                {impersonatingId === member.id ? "..." : "View as"}
                                            </button>
                                        )}
                                        {member.user_id && (
                                            <button
                                                onClick={() => { setAssigningId(assigningId === member.id ? null : member.id); setAssignRole(member.staff_role || "waiter"); }}
                                                className="text-[10px] px-2 py-1 rounded bg-surface-hover text-text-muted hover:text-accent transition-all">
                                                Set role
                                            </button>
                                        )}
                                        <button onClick={() => handleToggleActive(member)} disabled={submitting}
                                            className={`text-[10px] px-2 py-1 rounded transition-all ${member.is_active ? "bg-surface-hover text-text-muted hover:text-danger" : "bg-success/10 text-success"}`}>
                                            {member.is_active ? "Deactivate" : "Reactivate"}
                                        </button>
                                    </div>
                                </div>

                                <AnimatePresence>
                                    {assigningId === member.id && (
                                        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                                            className="mt-2 flex gap-2 items-center">
                                            <div className="flex-1 flex flex-col gap-1">
                                                <label htmlFor={`assign-role-${member.id}`} className="sr-only">Role for {member.name}</label>
                                                <select id={`assign-role-${member.id}`} value={assignRole} onChange={(e) => setAssignRole(e.target.value)}
                                                    className="w-full bg-surface-hover border border-border rounded-lg px-2 py-1.5 text-xs text-text focus:outline-none">
                                                    {STAFF_ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                                                </select>
                                            </div>
                                            <button onClick={() => handleAssignRole(member.id)} disabled={submitting}
                                                className="bg-accent text-black rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50">
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
