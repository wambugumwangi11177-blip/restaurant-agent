"use client";

/**
 * PageLoader — the centered accent spinner shown while auth/session state
 * resolves. Extracted from dashboard/layout.tsx so TierLayoutShell can show
 * the same thing instead of a blank `null` during load.
 */
export default function PageLoader() {
    return (
        <div className="min-h-screen flex items-center justify-center">
            <div className="w-6 h-6 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
        </div>
    );
}
