"use client";

import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Loader2, Eye, EyeOff } from "lucide-react";

export default function LoginPage() {
    const { login, register } = useAuth();
    const router = useRouter();
    const [isRegister, setIsRegister] = useState(false);
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [tenantName, setTenantName] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");
        setLoading(true);
        try {
            if (isRegister) {
                await register(email, password, tenantName);
            } else {
                await login(email, password);
            }
            router.push("/dashboard");
        } catch (err: unknown) {
            let message = "Authentication failed";
            if (err && typeof err === "object" && "response" in err) {
                const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string };
                message = axiosErr.response?.data?.detail || axiosErr.message || message;
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
                {/* Brand */}
                <div className="text-center mb-10">
                    <h1 className="text-3xl font-bold tracking-tight text-[#e5e5e5]">
                        Chakula
                    </h1>
                    <p className="text-sm text-[#737373] mt-1">Restaurant Manager</p>
                </div>

                {/* Card */}
                <div className="bg-[#141414] border border-[#262626] rounded-xl p-6">
                    <h2 className="text-lg font-semibold mb-5 text-[#e5e5e5]">
                        {isRegister ? "Create Account" : "Sign In"}
                    </h2>

                    {error && (
                        <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                            {error}
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className="space-y-4">
                        {isRegister && (
                            <div>
                                <label className="block text-sm text-[#737373] mb-1.5">Restaurant Name</label>
                                <input
                                    type="text"
                                    value={tenantName}
                                    onChange={(e) => setTenantName(e.target.value)}
                                    className="w-full px-3 py-2.5 rounded-lg bg-[#0a0a0a] border border-[#262626] focus:border-[#d4a853] outline-none text-[#e5e5e5] placeholder-[#525252] text-sm"
                                    placeholder="e.g. Mama Ngina's Kitchen"
                                    required
                                />
                            </div>
                        )}

                        <div>
                            <label className="block text-sm text-[#737373] mb-1.5">Email</label>
                            <input
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="w-full px-3 py-2.5 rounded-lg bg-[#0a0a0a] border border-[#262626] focus:border-[#d4a853] outline-none text-[#e5e5e5] placeholder-[#525252] text-sm"
                                placeholder="you@restaurant.com"
                                required
                            />
                        </div>

                        <div>
                            <label className="block text-sm text-[#737373] mb-1.5">Password</label>
                            <div className="relative">
                                <input
                                    type={showPassword ? "text" : "password"}
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    className="w-full px-3 py-2.5 rounded-lg bg-[#0a0a0a] border border-[#262626] focus:border-[#d4a853] outline-none text-[#e5e5e5] placeholder-[#525252] text-sm pr-10"
                                    placeholder="••••••••"
                                    required
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowPassword(!showPassword)}
                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-[#525252] hover:text-[#737373]"
                                >
                                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                </button>
                            </div>
                        </div>

                        <button
                            type="submit"
                            disabled={loading}
                            className="w-full py-2.5 rounded-lg bg-[#d4a853] hover:bg-[#e0b96a] text-[#0a0a0a] font-semibold text-sm flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {loading ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                            ) : isRegister ? (
                                "Create Account"
                            ) : (
                                "Sign In"
                            )}
                        </button>
                    </form>

                    <div className="mt-5 text-center">
                        <button
                            onClick={() => {
                                setIsRegister(!isRegister);
                                setError("");
                            }}
                            className="text-sm text-[#737373] hover:text-[#d4a853]"
                        >
                            {isRegister
                                ? "Already have an account? Sign in"
                                : "New restaurant? Create account"}
                        </button>
                    </div>
                </div>
            </motion.div>
        </div>
    );
}
