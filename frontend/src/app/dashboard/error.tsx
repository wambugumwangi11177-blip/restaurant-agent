"use client";

import { useEffect } from "react";
import { AlertTriangle } from "lucide-react";
import Button from "@/components/ui/Button";

// Audit remediation, Tier 4 item 9: this dashboard had no error boundary at
// any route level — a render crash under /dashboard/* fell straight through
// to Next.js's bare default screen. This file (the App Router's error
// boundary convention) catches any crash under this layout while the
// nav/sidebar chrome in dashboard/layout.tsx stays mounted, so a broken
// section doesn't take the whole app down with it.
//
// No frontend error-tracking service is wired into this project yet (Sentry
// exists on the backend only) — console.error is the best available signal
// until one is added; that's a separate decision, not bundled into this fix.
export default function DashboardError({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    useEffect(() => {
        console.error("[DashboardError]", error);
    }, [error]);

    return (
        <div className="flex items-center justify-center min-h-[60vh] px-6">
            <div className="max-w-sm text-center space-y-4">
                <AlertTriangle className="w-10 h-10 text-[var(--danger)] mx-auto" />
                <h1 className="text-lg font-semibold text-[var(--text)]">
                    Something went wrong on this page
                </h1>
                <p className="text-sm text-[var(--text-dim)]">
                    The rest of Chakula is still working — try again, or head back to
                    the dashboard home.
                </p>
                <div className="flex flex-wrap gap-3 justify-center pt-2">
                    <Button variant="primary" onClick={reset}>
                        Try again
                    </Button>
                    <Button variant="secondary" onClick={() => { window.location.href = "/dashboard"; }}>
                        Go to dashboard home
                    </Button>
                </div>
            </div>
        </div>
    );
}
