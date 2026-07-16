"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, Check } from "lucide-react";
import { useNotifications, NotificationItem } from "@/lib/useNotifications";

function timeAgo(iso: string): string {
    const then = new Date(iso).getTime();
    const diffMs = Date.now() - then;
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
}

export default function NotificationBell() {
    const {
        notifications, unreadCount, permission, subscribed, isIOSNotStandalone,
        markRead, markAllRead, subscribeToPush,
    } = useNotifications();
    const [open, setOpen] = useState(false);
    const panelRef = useRef<HTMLDivElement>(null);
    const router = useRouter();

    useEffect(() => {
        function onClickOutside(e: MouseEvent) {
            if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
                setOpen(false);
            }
        }
        if (open) document.addEventListener("mousedown", onClickOutside);
        return () => document.removeEventListener("mousedown", onClickOutside);
    }, [open]);

    const showEnableCta = permission !== "granted" && !subscribed;

    function handleClick(n: NotificationItem) {
        if (!n.is_read) markRead(n.id);
        setOpen(false);
        if (n.url) router.push(n.url);
    }

    return (
        <div className="relative" ref={panelRef}>
            <button
                onClick={() => setOpen((v) => !v)}
                aria-label="Notifications"
                className="relative text-[#737373] hover:text-[#e5e5e5] transition-colors"
            >
                <Bell className="w-5 h-5" />
                {unreadCount > 0 && (
                    <span className="absolute -top-1.5 -right-1.5 min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-white text-[10px] leading-4 text-center font-medium">
                        {unreadCount > 9 ? "9+" : unreadCount}
                    </span>
                )}
            </button>

            {open && (
                <div className="absolute right-0 mt-2 w-80 max-h-[28rem] overflow-y-auto bg-[#0f0f0f] border border-[#1a1a1a] rounded-lg shadow-xl z-50">
                    <div className="flex items-center justify-between px-3 py-2 border-b border-[#1a1a1a]">
                        <span className="text-xs font-medium text-[#e5e5e5]">Notifications</span>
                        {unreadCount > 0 && (
                            <button
                                onClick={() => markAllRead()}
                                className="text-[10px] text-[#737373] hover:text-[#e5e5e5] flex items-center gap-1"
                            >
                                <Check className="w-3 h-3" /> Mark all read
                            </button>
                        )}
                    </div>

                    {showEnableCta && (
                        <div className="px-3 py-2.5 border-b border-[#1a1a1a] bg-[#131313]">
                            {isIOSNotStandalone ? (
                                <p className="text-[11px] text-[#a3a3a3] leading-relaxed">
                                    To get notifications on iPhone: tap Share, then{" "}
                                    <span className="text-[#e5e5e5]">Add to Home Screen</span>, then open Chakula from
                                    there.
                                </p>
                            ) : permission === "denied" ? (
                                <p className="text-[11px] text-[#a3a3a3] leading-relaxed">
                                    Notifications are blocked in your browser settings.
                                </p>
                            ) : (
                                <button
                                    onClick={() => subscribeToPush()}
                                    className="w-full text-xs text-center py-1.5 rounded-md bg-[#1a1a1a] hover:bg-[#222] text-[#e5e5e5] transition-colors"
                                >
                                    Enable notifications
                                </button>
                            )}
                        </div>
                    )}

                    {notifications.length === 0 ? (
                        <div className="px-3 py-6 text-center text-xs text-[#525252]">
                            No notifications yet
                        </div>
                    ) : (
                        <ul>
                            {notifications.map((n) => (
                                <li key={n.id}>
                                    <button
                                        onClick={() => handleClick(n)}
                                        className={`w-full text-left px-3 py-2.5 border-b border-[#1a1a1a] hover:bg-[#151515] transition-colors ${
                                            n.is_read ? "" : "bg-[#111]"
                                        }`}
                                    >
                                        <div className="flex items-start gap-2">
                                            {!n.is_read && (
                                                <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" />
                                            )}
                                            <div className="flex-1 min-w-0">
                                                <p className="text-xs font-medium text-[#e5e5e5] truncate">{n.title}</p>
                                                <p className="text-[11px] text-[#737373] line-clamp-2 mt-0.5">{n.body}</p>
                                                <p className="text-[10px] text-[#525252] mt-1">{timeAgo(n.created_at)}</p>
                                            </div>
                                        </div>
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            )}
        </div>
    );
}
