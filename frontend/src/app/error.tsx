"use client";

// App Router error boundary (tech-debt D22). Before this, an uncaught render
// error anywhere under the root layout showed Next.js's default unbranded
// screen instead of something a restaurant floor staff member could actually
// act on mid-shift.

import { useEffect } from "react";
import { AlertTriangle } from "lucide-react";

export default function Error({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    useEffect(() => {
        console.error(error);
    }, [error]);

    return (
        <div className="min-h-screen flex items-center justify-center bg-[#0a0a0a] text-[#e5e5e5] p-6">
            <div className="max-w-sm w-full text-center space-y-4">
                <div className="mx-auto w-12 h-12 rounded-full bg-[#ef4444]/10 border border-[#ef4444]/30 flex items-center justify-center">
                    <AlertTriangle className="w-5 h-5 text-[#ef4444]" />
                </div>
                <div>
                    <h1 className="text-lg font-semibold">Something went wrong</h1>
                    <p className="text-sm text-[#a3a3a3] mt-1">
                        This screen hit an error. Your data is safe — try again.
                    </p>
                </div>
                <button
                    onClick={() => reset()}
                    className="px-5 py-2.5 rounded-xl text-sm font-semibold bg-[#d4a853] text-black hover:bg-[#c49843] transition-all"
                >
                    Try again
                </button>
            </div>
        </div>
    );
}
