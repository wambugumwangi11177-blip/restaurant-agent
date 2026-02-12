"use client";

import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Brain, Eye, EyeOff, Loader2 } from "lucide-react";

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
            const message =
                err instanceof Error ? err.message : "Authentication failed";
            setError(message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center px-4 relative overflow-hidden">
            {/* Background Effects */}
            <div className="absolute inset-0 bg-gradient-to-br from-indigo-950/50 via-gray-950 to-cyan-950/30" />
            <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-indigo-600/10 rounded-full blur-3xl" />
            <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-cyan-600/10 rounded-full blur-3xl" />

            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6 }}
                className="relative w-full max-w-md"
            >
                {/* Header */}
                <div className="text-center mb-8">
                    <motion.div
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        transition={{ delay: 0.2, type: "spring", stiffness: 200 }}
                        className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-indigo-600/20 border border-indigo-500/30 mb-4"
                    >
                        <Brain className="w-8 h-8 text-indigo-400" />
                    </motion.div>
                    <h1 className="text-3xl font-bold gradient-text">AI Restaurant OS</h1>
                    <p className="text-gray-400 mt-2">The Restaurant Brain</p>
                </div>

                {/* Card */}
                <div className="glass rounded-2xl p-8">
                    <h2 className="text-xl font-semibold mb-6">
                        {isRegister ? "Create Account" : "Welcome Back"}
                    </h2>

                    {error && (
                        <motion.div
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: "auto" }}
                            className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm"
                        >
                            {error}
                        </motion.div>
                    )}

                    <form onSubmit={handleSubmit} className="space-y-4">
                        {isRegister && (
                            <motion.div
                                initial={{ opacity: 0, height: 0 }}
                                animate={{ opacity: 1, height: "auto" }}
                            >
                                <label className="block text-sm text-gray-400 mb-1">Restaurant Name</label>
                                <input
                                    type="text"
                                    value={tenantName}
                                    onChange={(e) => setTenantName(e.target.value)}
                                    className="w-full px-4 py-3 rounded-xl bg-gray-800/50 border border-gray-700 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none transition-all text-white placeholder-gray-500"
                                    placeholder="My Restaurant"
                                    required
                                />
                            </motion.div>
                        )}

                        <div>
                            <label className="block text-sm text-gray-400 mb-1">Email</label>
                            <input
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="w-full px-4 py-3 rounded-xl bg-gray-800/50 border border-gray-700 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none transition-all text-white placeholder-gray-500"
                                placeholder="admin@restaurant.com"
                                required
                            />
                        </div>

                        <div>
                            <label className="block text-sm text-gray-400 mb-1">Password</label>
                            <div className="relative">
                                <input
                                    type={showPassword ? "text" : "password"}
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    className="w-full px-4 py-3 rounded-xl bg-gray-800/50 border border-gray-700 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none transition-all text-white placeholder-gray-500 pr-12"
                                    placeholder="••••••••"
                                    required
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowPassword(!showPassword)}
                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white transition-colors"
                                >
                                    {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                                </button>
                            </div>
                        </div>

                        <button
                            type="submit"
                            disabled={loading}
                            className="w-full py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition-all duration-200 flex items-center justify-center gap-2 glow-primary disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {loading ? (
                                <Loader2 className="w-5 h-5 animate-spin" />
                            ) : isRegister ? (
                                "Create Account"
                            ) : (
                                "Sign In"
                            )}
                        </button>
                    </form>

                    <div className="mt-6 text-center">
                        <button
                            onClick={() => {
                                setIsRegister(!isRegister);
                                setError("");
                            }}
                            className="text-sm text-gray-400 hover:text-indigo-400 transition-colors"
                        >
                            {isRegister
                                ? "Already have an account? Sign in"
                                : "Don't have an account? Create one"}
                        </button>
                    </div>
                </div>
            </motion.div>
        </div>
    );
}
