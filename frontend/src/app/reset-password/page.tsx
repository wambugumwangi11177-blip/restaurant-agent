"use client";

import { Suspense, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Loader2, Eye, EyeOff, CheckCircle2 } from "lucide-react";
import { motion } from "framer-motion";
import api from "@/lib/api";

function ResetPasswordForm() {
    const searchParams = useSearchParams();
    const router = useRouter();
    const token = searchParams.get("token") || "";

    const [password, setPassword] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const [loading, setLoading] = useState(false);
    const [done, setDone] = useState(false);
    const [error, setError] = useState("");

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");
        setLoading(true);
        try {
            await api.post("/api/v1/auth/password-reset/confirm", {
                token,
                new_password: password,
            });
            setDone(true);
            setTimeout(() => router.push("/login"), 2000);
        } catch (err: unknown) {
            let message = "This link is invalid or has expired.";
            if (err && typeof err === "object" && "response" in err) {
                const axiosErr = err as { response?: { data?: { detail?: string } } };
                message = axiosErr.response?.data?.detail || message;
            }
            setError(message);
        } finally {
            setLoading(false);
        }
    };

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
                    <p className="text-sm text-[#737373] mt-1">Set a new password</p>
                </div>

                <div className="bg-[#141414] border border-[#262626] rounded-xl p-6">
                    {!token ? (
                        <div className="text-center py-2">
                            <p className="text-sm text-red-400">
                                No reset token found. Use the link from your email.
                            </p>
                        </div>
                    ) : done ? (
                        <div className="text-center space-y-3 py-2">
                            <CheckCircle2 className="w-8 h-8 text-[var(--accent)] mx-auto" />
                            <p className="text-sm text-[#e5e5e5] font-medium">Password updated</p>
                            <p className="text-sm text-[#737373]">
                                All previous sessions were signed out. Redirecting to sign in&hellip;
                            </p>
                        </div>
                    ) : (
                        <>
                            <h2 className="text-lg font-semibold mb-5 text-[#e5e5e5]">New password</h2>

                            {error && (
                                <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                                    {error}
                                </div>
                            )}

                            <form onSubmit={handleSubmit} className="space-y-4">
                                <div>
                                    <label className="block text-sm text-[#737373] mb-1.5">New password</label>
                                    <div className="relative">
                                        <input
                                            type={showPassword ? "text" : "password"}
                                            value={password}
                                            onChange={(e) => setPassword(e.target.value)}
                                            className="w-full px-3 py-2.5 rounded-lg bg-[#0a0a0a] border border-[#262626] focus:border-[var(--accent)] outline-none text-[#e5e5e5] placeholder-[#525252] text-sm pr-10"
                                            placeholder="At least 8 characters, 1 letter, 1 number"
                                            required
                                        />
                                        <button
                                            type="button"
                                            onClick={() => setShowPassword(!showPassword)}
                                            aria-label={showPassword ? "Hide password" : "Show password"}
                                            className="absolute right-3 top-1/2 -translate-y-1/2 text-[#525252] hover:text-[#737373]"
                                        >
                                            {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                        </button>
                                    </div>
                                </div>

                                <button
                                    type="submit"
                                    disabled={loading}
                                    className="w-full py-2.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-[#0a0a0a] font-semibold text-sm flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Reset password"}
                                </button>
                            </form>
                        </>
                    )}

                    <div className="mt-5 text-center">
                        <a href="/login" className="text-sm text-[#737373] hover:text-[var(--accent)]">
                            Back to sign in
                        </a>
                    </div>
                </div>
            </motion.div>
        </div>
    );
}

export default function ResetPasswordPage() {
    return (
        <Suspense fallback={null}>
            <ResetPasswordForm />
        </Suspense>
    );
}
