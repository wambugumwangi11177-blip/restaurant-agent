"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Clock, LogIn } from "lucide-react";
import { useToast } from "@/components/ui/Toast";
import { getErrorMessage, isHttpStatus } from "@/lib/errors";

/**
 * Clock in/out — added to every staff tier's header (TierLayoutShell) so
 * it's universal rather than gated behind a domain nav entry, since
 * attendance applies to every tier equally (directive 015 has no matrix
 * row for it). GPS is opt-in: geolocation is asked for best-effort and the
 * clock-in still succeeds if it's denied or unavailable — see
 * routers/attendance.py's "flag, don't block" posture.
 */
interface AttendanceShift {
    id: number;
    clock_in: string;
    clock_out: string | null;
}

export default function AttendanceWidget() {
    const [status, setStatus] = useState<{ clocked_in: boolean; shift: AttendanceShift | null } | null>(null);
    const [loading, setLoading] = useState(false);
    const [linked, setLinked] = useState(true);
    const { showToast, toastNode } = useToast();

    const fetchStatus = async () => {
        try {
            const res = await api.get("/attendance/status");
            setStatus(res.data);
            setLinked(true);
        } catch (err) {
            // 400 = no StaffMember row linked to this account — hide the
            // widget rather than show a broken control (routers/attendance.py).
            if (isHttpStatus(err, 400)) setLinked(false);
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
            showToast(getErrorMessage(err, "Clock-in failed"), "error");
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
            showToast(getErrorMessage(err, "Clock-out failed"), "error");
        }
        setLoading(false);
    };

    if (!linked || !status) return null;

    return (
        <>
            {toastNode}
            {status.clocked_in ? (
                <button
                    onClick={handleClockOut}
                    disabled={loading}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-success/10 text-success border border-success/30 hover:bg-success/20 transition-all disabled:opacity-50"
                >
                    <Clock className="w-3 h-3" />
                    {loading ? "..." : "Clock Out"}
                </button>
            ) : (
                <button
                    onClick={handleClockIn}
                    disabled={loading}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-surface-hover text-text-muted border border-border hover:text-accent transition-all disabled:opacity-50"
                >
                    <LogIn className="w-3 h-3" />
                    {loading ? "..." : "Clock In"}
                </button>
            )}
        </>
    );
}
