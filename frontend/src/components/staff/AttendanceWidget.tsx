"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Clock, LogIn } from "lucide-react";

/**
 * Clock in/out — added to every staff tier's header (TierLayoutShell) so
 * it's universal rather than gated behind a domain nav entry, since
 * attendance applies to every tier equally (directive 015 has no matrix
 * row for it). GPS is opt-in: geolocation is asked for best-effort and the
 * clock-in still succeeds if it's denied or unavailable — see
 * routers/attendance.py's "flag, don't block" posture.
 */
export default function AttendanceWidget() {
    const [status, setStatus] = useState<{ clocked_in: boolean; shift: any | null } | null>(null);
    const [loading, setLoading] = useState(false);
    const [linked, setLinked] = useState(true);

    const fetchStatus = async () => {
        try {
            const res = await api.get("/attendance/status");
            setStatus(res.data);
            setLinked(true);
        } catch (err: any) {
            // 400 = no StaffMember row linked to this account — hide the
            // widget rather than show a broken control (routers/attendance.py).
            if (err?.response?.status === 400) setLinked(false);
        }
    };

    useEffect(() => { fetchStatus(); }, []);

    const getLocation = (): Promise<{ lat?: number; lng?: number }> =>
        new Promise((resolve) => {
            if (!navigator.geolocation) { resolve({}); return; }
            navigator.geolocation.getCurrentPosition(
                (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
                () => resolve({}),
                { timeout: 3000 }
            );
        });

    const handleClockIn = async () => {
        setLoading(true);
        try {
            const { lat, lng } = await getLocation();
            await api.post("/attendance/clock-in", { lat, lng });
            await fetchStatus();
        } catch (err) {
            console.error("Clock-in failed:", err);
        }
        setLoading(false);
    };

    const handleClockOut = async () => {
        setLoading(true);
        try {
            const { lat, lng } = await getLocation();
            await api.post("/attendance/clock-out", { lat, lng });
            await fetchStatus();
        } catch (err) {
            console.error("Clock-out failed:", err);
        }
        setLoading(false);
    };

    if (!linked || !status) return null;

    return status.clocked_in ? (
        <button
            onClick={handleClockOut}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-[#22c55e]/10 text-[#22c55e] border border-[#22c55e]/30 hover:bg-[#22c55e]/20 transition-all disabled:opacity-50"
        >
            <Clock className="w-3 h-3" />
            {loading ? "..." : "Clock Out"}
        </button>
    ) : (
        <button
            onClick={handleClockIn}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-[#1a1a1a] text-[#737373] border border-[#262626] hover:text-[var(--accent)] transition-all disabled:opacity-50"
        >
            <LogIn className="w-3 h-3" />
            {loading ? "..." : "Clock In"}
        </button>
    );
}
