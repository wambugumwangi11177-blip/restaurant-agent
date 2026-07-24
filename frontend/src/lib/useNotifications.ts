/**
 * frontend/src/lib/useNotifications.ts
 * In-app notification feed + Web Push subscription, built because Twilio is
 * unfunded — this channel costs nothing and needs no external account (see
 * backend/ai/notify.py). Polls GET /notifications on the same interval
 * pattern dashboard/kitchen/page.tsx already uses for order refresh.
 *
 * iOS note: Web Push only works on Safari when the dashboard has been added
 * to the Home Screen (Apple platform requirement, iOS 16.4+) — a plain
 * Safari tab can request permission but the subscription silently never
 * fires. isIOSNotStandalone lets the UI show an install instruction instead
 * of a permission prompt that would otherwise look broken.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import api from "@/lib/api";

export interface NotificationItem {
    id: number;
    title: string;
    body: string;
    event_type: string;
    url: string | null;
    is_read: boolean;
    created_at: string;
}

type PermissionState = "unsupported" | "default" | "granted" | "denied";

const POLL_INTERVAL_MS = 25000;

function urlBase64ToUint8Array(base64String: string): Uint8Array {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const rawData = atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; i++) outputArray[i] = rawData.charCodeAt(i);
    return outputArray;
}

function detectIOSNotStandalone(): boolean {
    if (typeof window === "undefined" || typeof navigator === "undefined") return false;
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
    // navigator.standalone is Safari-specific (not in the TS lib DOM types).
    const standalone = (window.navigator as Navigator & { standalone?: boolean }).standalone === true;
    return isIOS && !standalone;
}

export function useNotifications() {
    const [notifications, setNotifications] = useState<NotificationItem[]>([]);
    const [unreadCount, setUnreadCount] = useState(0);
    const [permission, setPermission] = useState<PermissionState>("unsupported");
    const [subscribed, setSubscribed] = useState(false);
    const [isIOSNotStandalone] = useState<boolean>(detectIOSNotStandalone);
    const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const fetchNotifications = useCallback(async () => {
        try {
            const res = await api.get("/notifications/", { params: { limit: 50 } });
            setNotifications(res.data.items || []);
            setUnreadCount(res.data.unread_count || 0);
        } catch {
            // Best-effort feed — a failed poll shouldn't surface an error UI;
            // it just tries again on the next interval.
        }
    }, []);

    useEffect(() => {
        if (typeof window === "undefined") return;
        setPermission(
            "Notification" in window ? (Notification.permission as PermissionState) : "unsupported"
        );

        fetchNotifications();
        intervalRef.current = setInterval(fetchNotifications, POLL_INTERVAL_MS);
        return () => {
            if (intervalRef.current) clearInterval(intervalRef.current);
        };
    }, [fetchNotifications]);

    const markRead = useCallback(async (id: number) => {
        setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
        setUnreadCount((c) => Math.max(0, c - 1));
        try {
            await api.post(`/notifications/${id}/read`);
        } catch {
            // Feed will self-correct on the next poll if this failed silently.
        }
    }, []);

    const markAllRead = useCallback(async () => {
        setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
        setUnreadCount(0);
        try {
            await api.post("/notifications/read-all");
        } catch {
            // Same self-correcting posture as markRead.
        }
    }, []);

    const subscribeToPush = useCallback(async () => {
        if (typeof window === "undefined" || !("serviceWorker" in navigator) || !("PushManager" in window)) {
            setPermission("unsupported");
            return false;
        }
        const vapidKey = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY;
        if (!vapidKey) {
            return false;
        }

        const perm = await Notification.requestPermission();
        setPermission(perm as PermissionState);
        if (perm !== "granted") return false;

        try {
            const registration = await navigator.serviceWorker.ready;
            let sub = await registration.pushManager.getSubscription();
            if (!sub) {
                sub = await registration.pushManager.subscribe({
                    userVisibleOnly: true,
                    // Cast: TS's lib.dom BufferSource type wants an
                    // ArrayBuffer-backed view specifically, but Uint8Array's
                    // declared buffer type is the broader ArrayBufferLike —
                    // this is a real runtime BufferSource (freshly allocated
                    // by urlBase64ToUint8Array, never a SharedArrayBuffer).
                    applicationServerKey: urlBase64ToUint8Array(vapidKey) as BufferSource,
                });
            }
            const json = sub.toJSON();
            await api.post("/notifications/subscribe", {
                endpoint: json.endpoint,
                p256dh: json.keys?.p256dh,
                auth: json.keys?.auth,
                user_agent: navigator.userAgent,
            });
            setSubscribed(true);
            return true;
        } catch {
            return false;
        }
    }, []);

    return {
        notifications,
        unreadCount,
        permission,
        subscribed,
        isIOSNotStandalone,
        markRead,
        markAllRead,
        subscribeToPush,
        refresh: fetchNotifications,
    };
}
