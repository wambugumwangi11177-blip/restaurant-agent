"use client";

import { useEffect } from "react";

// Audit remediation, Tier 4 item 9 — the last-resort catch-all. Only fires
// when a crash happens above dashboard/error.tsx's boundary (e.g. in the root
// layout itself), which is rare, so this intentionally doesn't pull in
// Providers/fonts/the rest of the app shell — per Next's App Router
// convention, global-error.tsx replaces the ENTIRE root layout on error and
// must render its own <html>/<body>, not assume the real one is still
// mounted around it.
export default function GlobalError({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    useEffect(() => {
        console.error("[GlobalError]", error);
    }, [error]);

    return (
        <html lang="en">
            <body
                style={{
                    background: "#0a0a0a",
                    color: "#e5e5e5",
                    fontFamily: "-apple-system, BlinkMacSystemFont, sans-serif",
                    minHeight: "100vh",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    padding: "24px",
                }}
            >
                <div style={{ maxWidth: 380, textAlign: "center" }}>
                    <h1 style={{ fontSize: 18, fontWeight: 600, marginBottom: 8 }}>
                        Chakula hit a problem
                    </h1>
                    <p style={{ fontSize: 14, color: "#a3a3a3", marginBottom: 20 }}>
                        Something went wrong loading the app. Try reloading — if it
                        keeps happening, contact support.
                    </p>
                    <button
                        onClick={reset}
                        style={{
                            background: "#d4a853",
                            color: "#0a0a0a",
                            fontWeight: 600,
                            border: "none",
                            borderRadius: 8,
                            padding: "10px 20px",
                            fontSize: 14,
                            cursor: "pointer",
                        }}
                    >
                        Reload
                    </button>
                </div>
            </body>
        </html>
    );
}
