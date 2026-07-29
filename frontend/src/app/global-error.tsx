"use client";

import { useEffect } from "react";
import { AlertTriangle } from "lucide-react";

/**
 * Catches errors thrown by the ROOT layout itself (error.tsx only covers
 * segments below it) — must render its own <html>/<body> since it replaces
 * the whole tree, including the layout that would normally provide them.
 */
export default function GlobalError({
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
        <html lang="en" className="dark">
            <body className="font-sans antialiased bg-[#0a0a0a] text-[#e5e5e5]">
                <div className="min-h-screen flex items-center justify-center px-4">
                    <div className="w-full max-w-sm bg-[#141414] border border-[#262626] rounded-xl p-6 text-center">
                        <AlertTriangle className="w-8 h-8 text-[#ef4444] mx-auto mb-3" />
                        <h1 className="text-lg font-semibold text-[#e5e5e5] mb-1">Something went wrong</h1>
                        <p className="text-sm text-[#7e7e7e] mb-5">
                            The app hit an unexpected error. Try reloading.
                        </p>
                        <button
                            onClick={reset}
                            className="px-4 py-2 rounded-lg bg-[#d4a853] hover:bg-[#e0b96a] text-[#0a0a0a] font-semibold text-sm"
                        >
                            Try again
                        </button>
                    </div>
                </div>
            </body>
        </html>
    );
}
