"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { motion } from "framer-motion";
import api from "@/lib/api";
import { getErrorMessage } from "@/lib/errors";

function VerifyEmailContent() {
    const searchParams = useSearchParams();
    const token = searchParams.get("token") || "";
    const [status, setStatus] = useState<"verifying" | "success" | "error">("verifying");
    const [message, setMessage] = useState("");

    useEffect(() => {
        if (!token) {
            setStatus("error");
            setMessage("No verification token found. Use the link from your email.");
            return;
        }
        api.post("/api/v1/auth/verify-email", { token })
            .then(() => setStatus("success"))
            .catch((err) => {
                setStatus("error");
                setMessage(getErrorMessage(err, "This link is invalid or has expired."));
            });
    }, [token]);

    return (
        <div className="min-h-screen flex items-center justify-center px-4 bg-[#0a0a0a]">
            <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4 }}
                className="w-full max-w-sm"
            >
                <div className="text-center mb-10">
                    <h1 className="text-3xl font-bold tracking-tight text-[#e5e5e5]">Chakula</h1>
                </div>

                <div className="bg-[#141414] border border-[#262626] rounded-xl p-6 text-center space-y-3">
                    {status === "verifying" && (
                        <>
                            <Loader2 className="w-8 h-8 text-[var(--accent)] mx-auto animate-spin" />
                            <p className="text-sm text-[#737373]">Verifying your email&hellip;</p>
                        </>
                    )}
                    {status === "success" && (
                        <>
                            <CheckCircle2 className="w-8 h-8 text-[var(--accent)] mx-auto" />
                            <p className="text-sm text-[#e5e5e5] font-medium">Email verified</p>
                            <p className="text-sm text-[#737373]">You&apos;re all set.</p>
                        </>
                    )}
                    {status === "error" && (
                        <>
                            <XCircle className="w-8 h-8 text-red-400 mx-auto" />
                            <p className="text-sm text-[#e5e5e5] font-medium">Verification failed</p>
                            <p className="text-sm text-[#737373]">{message}</p>
                        </>
                    )}

                    <a href="/dashboard" className="block mt-4 text-sm text-[var(--accent)] hover:underline">
                        Go to dashboard
                    </a>
                </div>
            </motion.div>
        </div>
    );
}

export default function VerifyEmailPage() {
    return (
        <Suspense fallback={null}>
            <VerifyEmailContent />
        </Suspense>
    );
}
