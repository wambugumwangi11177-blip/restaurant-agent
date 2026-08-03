"use client";

// Last-resort error boundary (tech-debt D22) for a crash in the root layout
// itself — Next.js requires this to render its own <html>/<body> since it
// replaces the whole document. Deliberately dependency-free (no icon import,
// no Tailwind reliance beyond inline styles) so this boundary has the
// smallest possible chance of failing itself.

import { useEffect } from "react";

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
        <html lang="en">
            <body
                style={{
                    minHeight: "100vh",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    background: "#0a0a0a",
                    color: "#e5e5e5",
                    fontFamily: "system-ui, sans-serif",
                    padding: "24px",
                }}
            >
                <div style={{ maxWidth: 360, width: "100%", textAlign: "center" }}>
                    <h1 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>Something went wrong</h1>
                    <p style={{ fontSize: 14, color: "#a3a3a3", marginTop: 8 }}>
                        The app hit an unexpected error. Your data is safe — try reloading.
                    </p>
                    <button
                        onClick={() => reset()}
                        style={{
                            marginTop: 16,
                            padding: "10px 20px",
                            borderRadius: 12,
                            fontSize: 14,
                            fontWeight: 600,
                            background: "#d4a853",
                            color: "#000",
                            border: "none",
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
