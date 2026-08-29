"use client";

import { useState } from "react";
import { Loader2, MailCheck } from "lucide-react";
import { motion } from "framer-motion";
import api from "@/lib/api";

export default function ForgotPasswordPage() {
    const [email, setEmail] = useState("");
    const [loading, setLoading] = useState(false);
    const [sent, setSent] = useState(false);
    const [error, setError] = useState("");

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");
        setLoading(true);
        try {
            // The backend always returns the same generic response whether
            // or not the email is registered (account-enumeration prevention)
            // — so the UI shows the same "check your inbox" state either way.
            await api.post("/api/v1/auth/password-reset/request", { email });
            setSent(true);
        } catch {
            setError("Something went wrong. Please try again.");
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
                    <p className="text-sm text-[#737373] mt-1">Reset your password</p>
                </div>

                <div className="bg-[#141414] border border-[#262626] rounded-xl p-6">
                    {sent ? (
                        <div className="text-center space-y-3 py-2">
                            <MailCheck className="w-8 h-8 text-[var(--accent)] mx-auto" />
                            <p className="text-sm text-[#e5e5e5] font-medium">Check your email</p>
                            <p className="text-sm text-[#737373]">
                                If an account exists for <span className="text-[#a3a3a3]">{email}</span>, a
                                password reset link is on its way. The link expires in 30 minutes.
                            </p>
                        </div>
                    ) : (
                        <>
                            <h2 className="text-lg font-semibold mb-5 text-[#e5e5e5]">Forgot password?</h2>
                            <p className="text-sm text-[#737373] mb-4">
                                Enter the email you signed up with and we&apos;ll send you a reset link.
                            </p>

                            {error && (
                                <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                                    {error}
                                </div>
                            )}

                            <form onSubmit={handleSubmit} className="space-y-4">
                                <div>
                                    <label className="block text-sm text-[#737373] mb-1.5">Email</label>
                                    <input
                                        type="email"
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        className="w-full px-3 py-2.5 rounded-lg bg-[#0a0a0a] border border-[#262626] focus:border-[var(--accent)] outline-none text-[#e5e5e5] placeholder-[#525252] text-sm"
                                        placeholder="you@restaurant.com"
                                        required
                                    />
                                </div>

                                <button
                                    type="submit"
                                    disabled={loading}
                                    className="w-full py-2.5 rounded-lg bg-[var(--accent)] hover:bg-[var(--accent-hover)] text-[#0a0a0a] font-semibold text-sm flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Send reset link"}
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
