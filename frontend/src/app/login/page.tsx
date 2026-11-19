"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { homeFor } from "@/lib/tenantHome";
import { PRODUCT_NAME, PRODUCT_TAGLINE } from "@/lib/brand";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Loader2, Eye, EyeOff, ArrowRight } from "lucide-react";

export default function LoginPage() {
    const { login, setInitialPassword } = useAuth();
    const router = useRouter();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const [firstPassword, setFirstPassword] = useState(false);
    const [nativeStore, setNativeStore] = useState(false);

    useEffect(() => {
        setNativeStore(navigator.userAgent.includes("LEVIIIStore"));
    }, []);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");
        setLoading(true);
        try {
            const signedIn = firstPassword
                ? await setInitialPassword(email, password)
                : await login(email, password);
            router.replace(homeFor(signedIn?.tenant_name, signedIn?.staff_role));
        } catch (err: unknown) {
            let message = "Authentication failed";
            if (err && typeof err === "object" && "response" in err) {
                const axiosErr = err as { response?: { data?: { detail?: string | { code?: string; email?: string } } }; message?: string };
                const rawDetail = axiosErr.response?.data?.detail;
                message = (typeof rawDetail === "string" ? rawDetail : rawDetail?.code) || axiosErr.message || message;
                const firstRequired =
                    rawDetail === "FIRST_PASSWORD_REQUIRED" ||
                    (typeof rawDetail === "object" && rawDetail?.code === "FIRST_PASSWORD_REQUIRED");
                if (firstRequired) {
                    setFirstPassword(true);
                    if (typeof rawDetail === "object" && rawDetail.email) {
                        setEmail(rawDetail.email);
                    }
                    setError("Choose your own password. This is your first sign-in.");
                    return;
                }
            } else if (err instanceof Error) {
                message = err.message;
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
                    <h1 className="text-3xl font-bold tracking-tight text-[#e5e5e5]">
                        {PRODUCT_NAME}
                    </h1>
                    <p className="text-sm text-[#737373] mt-1">{PRODUCT_TAGLINE}</p>
                </div>

                <div className="bg-[#141414] border border-[#262626] rounded-xl p-6">
                    <h2 className="text-lg font-semibold mb-5 text-[#e5e5e5]">
                        {firstPassword ? "Set your password" : "Sign in"}
                    </h2>

                    {error && (
                        <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                            {error}
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div>
                            <label htmlFor="email" className="block text-sm text-[#737373] mb-1.5">Email</label>
                            <input
                                id="email"
                                type="text"
                                inputMode="email"
                                autoComplete="username"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="w-full px-3 py-2.5 rounded-lg bg-[#0a0a0a] border border-[#262626] focus:border-[var(--accent)] outline-none text-[#e5e5e5] placeholder-[#525252] text-sm"
                                placeholder={nativeStore ? "jack@eleven.leviii" : "you@eleven.leviii"}
                                required
                            />
                        </div>

                        <div>
                            <label htmlFor="password" className="block text-sm text-[#737373] mb-1.5">Password</label>
                            <div className="relative">
                                <input
                                    id="password"
                                    type={showPassword ? "text" : "password"}
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    className="w-full px-3 py-2.5 rounded-lg bg-[#0a0a0a] border border-[#262626] focus:border-[var(--accent)] outline-none text-[#e5e5e5] placeholder-[#525252] text-sm pr-10"
                                    placeholder="••••••••"
                                    autoComplete={firstPassword ? "new-password" : "current-password"}
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
                            className="w-full min-h-11 py-2.5 rounded-lg bg-[#e8bd68] hover:bg-[#f3cf84] text-[#17120a] font-semibold text-sm flex items-center justify-center gap-2 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#e8bd68] disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {loading ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                            ) : firstPassword ? (
                                "Set password and sign in"
                            ) : (
                                <>Sign in <ArrowRight className="w-4 h-4" aria-hidden="true" /></>
                            )}
                        </button>
                    </form>

                </div>
            </motion.div>
        </div>
    );
}