"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AlertTriangle, X } from "lucide-react";
import { SUBSCRIPTION_INACTIVE_EVENT } from "@/lib/api";

/**
 * Listens for the 402 event api.ts dispatches on any /ai/* call and shows a
 * persistent renew banner. Mounted once in the dashboard layout rather than
 * threaded through every page that calls /ai/* — those pages mostly swallow
 * fetch errors with `.catch(() => {})`, so without this a lapsed subscription
 * would just look like "no data yet" with no way to tell the difference.
 *
 * Dismissible for the session (a staff member on the floor doesn't need to
 * see a billing prompt they can't act on), but re-appears on the next 402 —
 * dismissing doesn't mean fixed.
 */
export default function SubscriptionBanner() {
    const pathname = usePathname();
    const [visible, setVisible] = useState(false);
    const [dismissed, setDismissed] = useState(false);
    const [detail, setDetail] = useState<{ status?: string; plan?: string } | null>(null);

    useEffect(() => {
        const handler = (e: Event) => {
            setDetail((e as CustomEvent).detail || null);
            setVisible(true);
            setDismissed(false);
        };
        window.addEventListener(SUBSCRIPTION_INACTIVE_EVENT, handler);
        return () => window.removeEventListener(SUBSCRIPTION_INACTIVE_EVENT, handler);
    }, []);

    // Already on the billing page — the page itself explains the state.
    if (pathname?.startsWith("/dashboard/billing")) return null;
    if (!visible || dismissed) return null;

    return (
        <AnimatePresence>
            <motion.div
                initial={{ opacity: 0, y: -12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -12 }}
                className="mx-5 mt-3 flex items-center gap-3 px-4 py-2.5 bg-[#ef4444]/10 border border-[#ef4444]/30 rounded-xl"
            >
                <AlertTriangle className="w-4 h-4 text-[#ef4444] flex-shrink-0" />
                <p className="flex-1 text-xs text-[#e5e5e5]">
                    Your subscription {detail?.status === "past_due" ? "has lapsed" : "is inactive"} — AI insights,
                    pricing recommendations and reports are paused. Orders, POS and Kitchen keep working as normal.
                </p>
                <Link href="/dashboard/billing"
                    className="text-xs font-semibold text-[#ef4444] hover:underline whitespace-nowrap">
                    Renew now
                </Link>
                <button onClick={() => setDismissed(true)} className="text-[#737373] hover:text-[#e5e5e5]">
                    <X className="w-3.5 h-3.5" />
                </button>
            </motion.div>
        </AnimatePresence>
    );
}
