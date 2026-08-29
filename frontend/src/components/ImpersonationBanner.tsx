"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";

/**
 * Persistent, unmissable banner while an Owner is running a real
 * impersonation session (see AuthContext.startImpersonation/endImpersonation
 * and backend/routers/staff.py's /impersonate). Renders null the rest of the
 * time. Deliberately mounted once at the app root (Providers), not per
 * tier-layout, so it can't be missed on any page the impersonated session
 * reaches — the whole point is that it must never look like the Owner
 * "became invisible".
 */
export default function ImpersonationBanner() {
    const { user, endImpersonation } = useAuth();
    const router = useRouter();
    const [ending, setEnding] = useState(false);

    const impersonation = user?.impersonation ?? null;

    // expires_at isn't returned by /auth/me today — the countdown here is
    // cosmetic (server-side expiry is what's actually enforced); we just
    // don't want to promise a number we don't have. Show elapsed instead.
    const [secondsSinceStart, setSecondsSinceStart] = useState(0);
    const sessionId = impersonation?.session_id ?? null;
    useEffect(() => {
        if (!sessionId) return;
        setSecondsSinceStart(0);
        const id = setInterval(() => setSecondsSinceStart((s) => s + 1), 1000);
        return () => clearInterval(id);
    }, [sessionId]);

    if (!impersonation) return null;

    const mm = String(Math.floor(secondsSinceStart / 60)).padStart(2, "0");
    const ss = String(secondsSinceStart % 60).padStart(2, "0");

    const handleEnd = async () => {
        setEnding(true);
        try {
            await endImpersonation();
            router.push("/dashboard");
        } finally {
            setEnding(false);
        }
    };

    return (
        <div className="sticky top-0 z-[100] w-full bg-amber-500 text-black text-sm px-4 py-2 flex items-center justify-between gap-3 flex-wrap">
            <span className="font-medium">
                Viewing as {user?.email} ({user?.staff_role ?? "staff"}) — as {impersonation.impersonator_email} — {mm}:{ss} elapsed
            </span>
            <button
                onClick={handleEnd}
                disabled={ending}
                className="bg-black text-amber-400 rounded px-3 py-1 text-xs font-semibold hover:bg-black/80 disabled:opacity-50"
            >
                {ending ? "Ending…" : "End impersonation"}
            </button>
        </div>
    );
}
