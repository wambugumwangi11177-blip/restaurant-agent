"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import {
    Users, Plus, X, Loader2, LogIn, LogOut, Clock, UserX,
} from "lucide-react";

interface StaffMember {
    id: number;
    name: string;
    role_title: string;
    hourly_rate: number; // cents/hour
    is_active: boolean;
}

interface Shift {
    id: number;
    staff_member_id: number;
    staff_name: string;
    shift_date: string;
    scheduled_start: string | null;
    scheduled_end: string | null;
    actual_start: string | null;
    actual_end: string | null;
    actual_hours: number | null;
    labor_cost: number | null; // cents
}

const todayStr = () => new Date().toISOString().slice(0, 10);

export default function StaffPage() {
    const { user } = useAuth();
    const isAdmin = ((user as any)?.role || "").toLowerCase() !== "staff";

    const [staff, setStaff] = useState<StaffMember[]>([]);
    const [shifts, setShifts] = useState<Shift[]>([]);
    const [loading, setLoading] = useState(true);
    const [busyShiftId, setBusyShiftId] = useState<number | null>(null);
    const [toast, setToast] = useState("");

    const [showAddStaff, setShowAddStaff] = useState(false);
    const [newName, setNewName] = useState("");
    const [newRole, setNewRole] = useState("");
    const [newRateKes, setNewRateKes] = useState("");
    const [savingStaff, setSavingStaff] = useState(false);

    const [scheduleFor, setScheduleFor] = useState<number | "">("");
    const [scheduling, setScheduling] = useState(false);

    const fetchAll = async () => {
        const [staffRes, shiftRes] = await Promise.all([
            api.get("/staff/").catch(() => ({ data: [] })),
            api.get("/staff/shifts/", { params: { start_date: todayStr(), end_date: todayStr() } }).catch(() => ({ data: [] })),
        ]);
        setStaff(staffRes.data || []);
        setShifts(shiftRes.data || []);
        setLoading(false);
    };

    useEffect(() => { fetchAll(); }, []);

    const showToast = (msg: string) => {
        setToast(msg);
        setTimeout(() => setToast(""), 2500);
    };

    const formatKES = (cents: number) => `KES ${(cents / 100).toLocaleString("en-KE", { maximumFractionDigits: 0 })}`;
    const formatTime = (iso: string | null) => iso ? new Date(iso).toLocaleTimeString("en-KE", { hour: "2-digit", minute: "2-digit" }) : "—";

    const handleAddStaff = async () => {
        if (!newName) return;
        setSavingStaff(true);
        try {
            await api.post("/staff/", {
                name: newName,
                role_title: newRole,
                hourly_rate: Math.round((parseFloat(newRateKes) || 0) * 100), // KES entered, cents stored
            });
            setNewName(""); setNewRole(""); setNewRateKes("");
            setShowAddStaff(false);
            showToast(`Added ${newName} to the team`);
            await fetchAll();
        } catch { }
        setSavingStaff(false);
    };

    const handleDeactivate = async (member: StaffMember) => {
        try {
            await api.delete(`/staff/${member.id}`);
            showToast(`${member.name} removed from the active roster`);
            await fetchAll();
        } catch { }
    };

    const handleSchedule = async () => {
        if (!scheduleFor) return;
        setScheduling(true);
        try {
            await api.post("/staff/shifts/", {
                staff_member_id: scheduleFor,
                shift_date: todayStr(),
            });
            setScheduleFor("");
            showToast("Shift scheduled for today");
            await fetchAll();
        } catch { }
        setScheduling(false);
    };

    const handleClockIn = async (shift: Shift) => {
        setBusyShiftId(shift.id);
        try {
            await api.post(`/staff/shifts/${shift.id}/clock-in`);
            await fetchAll();
        } catch { }
        setBusyShiftId(null);
    };

    const handleClockOut = async (shift: Shift) => {
        setBusyShiftId(shift.id);
        try {
            await api.post(`/staff/shifts/${shift.id}/clock-out`);
            showToast("Clocked out");
            await fetchAll();
        } catch { }
        setBusyShiftId(null);
    };

    const scheduledStaffIds = new Set(shifts.map((s) => s.staff_member_id));
    const unscheduledStaff = staff.filter((s) => s.is_active && !scheduledStaffIds.has(s.id));

    if (loading) {
        return (
            <div className="space-y-3">
                {[...Array(4)].map((_, i) => (
                    <div key={i} className="bg-[#141414] rounded-xl h-16 animate-pulse" />
                ))}
            </div>
        );
    }

    return (
        <div className="space-y-5">
            <AnimatePresence>
                {toast && (
                    <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}
                        className="fixed top-4 right-4 z-50 bg-[#22c55e]/10 border border-[#22c55e]/30 rounded-xl px-5 py-3 text-sm text-[#22c55e]">
                        {toast}
                    </motion.div>
                )}
            </AnimatePresence>

            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-xl font-bold text-[#e5e5e5]">Staff</h1>
                    <p className="text-sm text-[#525252] mt-0.5">Clock in and out, and keep the roster up to date</p>
                </div>
                {isAdmin && (
                    <button onClick={() => setShowAddStaff(!showAddStaff)}
                        className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[#d4a853] hover:bg-[#e0b96a] text-[#0a0a0a] text-sm font-medium transition-colors">
                        {showAddStaff ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
                        {showAddStaff ? "Cancel" : "Add Staff"}
                    </button>
                )}
            </div>

            {/* Add staff form — admin only: wages are payroll data */}
            {isAdmin && showAddStaff && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
                    className="bg-[#141414] border border-[#262626] rounded-xl p-4 space-y-3">
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        <input placeholder="Name" value={newName} onChange={(e) => setNewName(e.target.value)}
                            className="col-span-2 sm:col-span-1 bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[#d4a853]/50 focus:outline-none" />
                        <input placeholder="Role (e.g. Waiter)" value={newRole} onChange={(e) => setNewRole(e.target.value)}
                            className="bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[#d4a853]/50 focus:outline-none" />
                        <input placeholder="KES / hour" type="number" value={newRateKes} onChange={(e) => setNewRateKes(e.target.value)}
                            className="bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-2 text-xs text-[#e5e5e5] placeholder-[#525252] focus:border-[#d4a853]/50 focus:outline-none" />
                        <button onClick={handleAddStaff} disabled={!newName || savingStaff}
                            className="bg-[#d4a853] text-black rounded-lg px-3 py-2 text-xs font-semibold disabled:opacity-50">
                            {savingStaff ? "Adding..." : "Add"}
                        </button>
                    </div>
                </motion.div>
            )}

            {/* Today's shifts — clock in/out, open to everyone on shift */}
            <div className="bg-[#141414] border border-[#262626] rounded-xl">
                <div className="px-4 py-3 border-b border-[#1a1a1a] flex items-center gap-2">
                    <Clock className="w-3.5 h-3.5 text-[#d4a853]" />
                    <p className="text-xs font-semibold text-[#e5e5e5]">Today&apos;s Shifts</p>
                </div>

                {isAdmin && unscheduledStaff.length > 0 && (
                    <div className="px-4 py-3 border-b border-[#1a1a1a] flex items-center gap-2">
                        <select value={scheduleFor} onChange={(e) => setScheduleFor(e.target.value ? Number(e.target.value) : "")}
                            className="flex-1 bg-[#1a1a1a] border border-[#262626] rounded-lg px-3 py-1.5 text-xs text-[#e5e5e5] focus:border-[#d4a853]/50 focus:outline-none">
                            <option value="">Schedule someone in for today...</option>
                            {unscheduledStaff.map((s) => (
                                <option key={s.id} value={s.id}>{s.name}{s.role_title ? ` — ${s.role_title}` : ""}</option>
                            ))}
                        </select>
                        <button onClick={handleSchedule} disabled={!scheduleFor || scheduling}
                            className="bg-[#d4a853]/10 text-[#d4a853] border border-[#d4a853]/30 rounded-lg px-3 py-1.5 text-xs font-medium disabled:opacity-50">
                            {scheduling ? "..." : "Add to today"}
                        </button>
                    </div>
                )}

                {shifts.length === 0 ? (
                    <p className="text-xs text-[#525252] text-center py-8">
                        Nobody&apos;s scheduled for today yet{isAdmin ? " — add someone above" : ""}.
                    </p>
                ) : (
                    <div className="divide-y divide-[#1a1a1a]">
                        {shifts.map((shift) => {
                            const isBusy = busyShiftId === shift.id;
                            const isIn = !!shift.actual_start && !shift.actual_end;
                            const isDone = !!shift.actual_end;
                            return (
                                <div key={shift.id} className="px-4 py-3 flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                        <div className={`w-2 h-2 rounded-full flex-shrink-0 ${isIn ? "bg-[#22c55e] animate-pulse" : isDone ? "bg-[#525252]" : "bg-[#eab308]"}`} />
                                        <div>
                                            <p className="text-sm text-[#e5e5e5]">{shift.staff_name}</p>
                                            <p className="text-[10px] text-[#525252]">
                                                {shift.actual_start
                                                    ? `In ${formatTime(shift.actual_start)}${shift.actual_end ? ` · Out ${formatTime(shift.actual_end)}` : ""}`
                                                    : "Not clocked in yet"}
                                                {isDone && shift.labor_cost != null && (
                                                    <> · {shift.actual_hours?.toFixed(1)}h · {formatKES(shift.labor_cost)}</>
                                                )}
                                            </p>
                                        </div>
                                    </div>
                                    {isDone ? (
                                        <span className="text-[10px] text-[#525252] uppercase tracking-wider">Done</span>
                                    ) : isIn ? (
                                        <button onClick={() => handleClockOut(shift)} disabled={isBusy}
                                            className="flex items-center gap-1.5 text-[10px] px-3 py-1.5 rounded-lg bg-[#ef4444]/10 text-[#ef4444] hover:bg-[#ef4444]/20 disabled:opacity-50 transition-all">
                                            {isBusy ? <Loader2 className="w-3 h-3 animate-spin" /> : <LogOut className="w-3 h-3" />}
                                            Clock Out
                                        </button>
                                    ) : (
                                        <button onClick={() => handleClockIn(shift)} disabled={isBusy}
                                            className="flex items-center gap-1.5 text-[10px] px-3 py-1.5 rounded-lg bg-[#22c55e]/10 text-[#22c55e] hover:bg-[#22c55e]/20 disabled:opacity-50 transition-all">
                                            {isBusy ? <Loader2 className="w-3 h-3 animate-spin" /> : <LogIn className="w-3 h-3" />}
                                            Clock In
                                        </button>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>

            {/* Roster — admin only: wages are payroll data */}
            {isAdmin && (
                <div className="bg-[#141414] border border-[#262626] rounded-xl">
                    <div className="px-4 py-3 border-b border-[#1a1a1a] flex items-center gap-2">
                        <Users className="w-3.5 h-3.5 text-[#d4a853]" />
                        <p className="text-xs font-semibold text-[#e5e5e5]">Team</p>
                    </div>
                    {staff.filter((s) => s.is_active).length === 0 ? (
                        <p className="text-xs text-[#525252] text-center py-8">No staff added yet.</p>
                    ) : (
                        <div className="divide-y divide-[#1a1a1a]">
                            {staff.filter((s) => s.is_active).map((member) => (
                                <div key={member.id} className="px-4 py-3 flex items-center justify-between">
                                    <div>
                                        <p className="text-sm text-[#e5e5e5]">{member.name}</p>
                                        <p className="text-[10px] text-[#525252]">
                                            {member.role_title || "Staff"} · {formatKES(member.hourly_rate)}/hr
                                        </p>
                                    </div>
                                    <button onClick={() => handleDeactivate(member)}
                                        title="Remove from active roster — their shift history is kept"
                                        className="text-[10px] px-2 py-1 rounded bg-[#1a1a1a] text-[#737373] hover:text-[#ef4444] flex items-center gap-1 transition-all">
                                        <UserX className="w-3 h-3" /> Remove
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
