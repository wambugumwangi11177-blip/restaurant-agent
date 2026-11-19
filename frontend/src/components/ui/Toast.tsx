"use client";

import { useCallback, useState } from "react";
import { Check, AlertTriangle } from "lucide-react";

export type ToastType = "success" | "error";

const VARIANTS: Record<ToastType, { icon: typeof Check; className: string }> = {
    success: {
        icon: Check,
        className: "bg-[var(--success)]/10 border-[var(--success)]/30 text-[var(--success)]",
    },
    error: {
        icon: AlertTriangle,
        className: "bg-[var(--danger)]/10 border-[var(--danger)]/30 text-[var(--danger)]",
    },
};

export function useToast() {
    const [toast, setToast] = useState<{ message: string; type: ToastType } | null>(null);

    const showToast = useCallback((message: string, type: ToastType = "success") => {
        setToast({ message, type });
        setTimeout(() => setToast((current) => (current?.message === message ? null : current)), 3000);
    }, []);

    const toastNode = toast ? (
        <div
            role="status"
            className={`fixed top-4 right-4 z-50 rounded-xl border px-5 py-3 flex items-center gap-2 ${VARIANTS[toast.type].className}`}
        >
            {(() => {
                const Icon = VARIANTS[toast.type].icon;
                return <Icon className="w-4 h-4" />;
            })()}
            <span className="text-sm">{toast.message}</span>
        </div>
    ) : null;

    return { showToast, toastNode };
}