"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { WifiOff, Wifi, RefreshCw, AlertTriangle } from "lucide-react";
import { listPendingOrders } from "@/lib/offlineQueue";
import { syncPendingOrders, OFFLINE_SYNC_EVENT, type SyncEventDetail } from "@/lib/offlineSync";

/**
 * Lives on the POS page. Shows three things a waiter on a flaky connection
 * actually needs to know at a glance: are we online right now, are there
 * orders waiting to leave this device, and did the last sync attempt fail.
 *
 * Deliberately silent (renders nothing) when there's nothing pending and the
 * connection is fine — this must not become permanent visual noise on every
 * healthy shift.
 */
export default function OfflineSyncIndicator() {
    const [online, setOnline] = useState(true);
    const [pendingCount, setPendingCount] = useState(0);
    const [failedCount, setFailedCount] = useState(0);
    const [syncing, setSyncing] = useState(false);

    const refreshPending = async () => {
        const pending = await listPendingOrders();
        setPendingCount(pending.length);
        setFailedCount(pending.filter((o) => o.attempts > 0).length);
    };

    useEffect(() => {
        setOnline(typeof navigator !== "undefined" ? navigator.onLine : true);
        refreshPending();

        const onOnline = () => setOnline(true);
        const onOffline = () => setOnline(false);
        window.addEventListener("online", onOnline);
        window.addEventListener("offline", onOffline);

        const onSyncEvent = (e: Event) => {
            const detail = (e as CustomEvent<SyncEventDetail>).detail;
            if (detail.phase === "start") setSyncing(true);
            if (detail.phase === "done") setSyncing(false);
            refreshPending();
        };
        window.addEventListener(OFFLINE_SYNC_EVENT, onSyncEvent);

        return () => {
            window.removeEventListener("online", onOnline);
            window.removeEventListener("offline", onOffline);
            window.removeEventListener(OFFLINE_SYNC_EVENT, onSyncEvent);
        };
    }, []);

    const handleSyncNow = async () => {
        setSyncing(true);
        await syncPendingOrders();
        setSyncing(false);
        refreshPending();
    };

    if (online && pendingCount === 0) return null;

    return (
        <AnimatePresence>
            <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border mb-3 ${!online
                        ? "bg-[#eab308]/10 border-[#eab308]/30"
                        : failedCount > 0
                            ? "bg-[#ef4444]/10 border-[#ef4444]/30"
                            : "bg-[#3b82f6]/10 border-[#3b82f6]/30"
                    }`}
            >
                {!online ? (
                    <WifiOff className="w-3.5 h-3.5 text-[#eab308] flex-shrink-0" />
                ) : failedCount > 0 ? (
                    <AlertTriangle className="w-3.5 h-3.5 text-[#ef4444] flex-shrink-0" />
                ) : (
                    <Wifi className="w-3.5 h-3.5 text-[#3b82f6] flex-shrink-0" />
                )}

                <span className={`text-[11px] flex-1 ${!online ? "text-[#eab308]" : failedCount > 0 ? "text-[#ef4444]" : "text-[#3b82f6]"}`}>
                    {!online
                        ? `No connection — orders are being saved on this device${pendingCount > 0 ? ` (${pendingCount} waiting)` : ""}`
                        : failedCount > 0
                            ? `${failedCount} order${failedCount !== 1 ? "s" : ""} couldn't sync — check them below`
                            : `${pendingCount} order${pendingCount !== 1 ? "s" : ""} syncing...`}
                </span>

                {online && pendingCount > 0 && (
                    <button
                        onClick={handleSyncNow}
                        disabled={syncing}
                        className="flex items-center gap-1 text-[10px] font-medium text-[#e5e5e5] bg-[#1a1a1a] hover:bg-[#262626] rounded px-2 py-1 disabled:opacity-50 transition-colors"
                    >
                        <RefreshCw className={`w-3 h-3 ${syncing ? "animate-spin" : ""}`} />
                        {syncing ? "Syncing..." : "Sync now"}
                    </button>
                )}
            </motion.div>
        </AnimatePresence>
    );
}
