"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { homeFor } from "@/lib/tenantHome";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Loader2, Eye, EyeOff, ArrowRight } from "lucide-react";

export default function LoginPage() {
    const { login, loginWithRestaurant, register } = useAuth();
    const router = useRouter();
    const [isRegister, setIsRegister] = useState(false);
    const [useEmailLogin, setUseEmailLogin] = useState(false);
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [tenantName, setTenantName] = useState("");
    const [restaurantName, setRestaurantName] = useState("Vibanda Village");
    const [showPassword, setShowPassword] = useState(false);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const [showGeneralLoginOptions, setShowGeneralLoginOptions] = useState(false);

    useEffect(() => {
        setShowGeneralLoginOptions(window.location.hostname !== "vibandavillage.vercel.app");
    }, []);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");
        setLoading(true);
        try {
            // Route on the user THIS call returned, never on the `user` state
            // read from the enclosing closure: React has not committed the
            // setUser() from login()/register() by the time this line runs, so
            // `user` is still the previous value (null on a first login). That
            // made homeFor() fall through to /dashboard for every account,
            // including Vibanda — the generic dashboard would paint, then its
            // layout's isVibanda() effect bounced to /vibanda. That flash is
            // the "it shows the old dashboard first, then the new one".
            const signedIn = isRegister
                ? await register(email, password, tenantName)
                : useEmailLogin
                    ? await login(email, password)
                    : await loginWithRestaurant(restaurantName, password);
            router.replace(homeFor(signedIn?.tenant_name));
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
                                <label htmlFor="signup-restaurant-name" className="block text-sm text-[#737373] mb-1.5">Restaurant Name</label>
                                <input
                                    id="signup-restaurant-name"
                                    type="text"
                                    value={tenantName}
                                    onChange={(e) => setTenantName(e.target.value)}
                                    className="w-full px-3 py-2.5 rounded-lg bg-[#0a0a0a] border border-[#262626] focus:border-[var(--accent)] outline-none text-[#e5e5e5] placeholder-[#525252] text-sm"
                                    placeholder="e.g. Mama Ngina's Kitchen"
                                    required
                                />
                            </div>
                        )}

                        {isRegister || useEmailLogin ? (
                            <div>
                                <label htmlFor="email" className="block text-sm text-[#737373] mb-1.5">Email</label>
                                <input
                                    id="email"
                                    type="email"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    className="w-full px-3 py-2.5 rounded-lg bg-[#0a0a0a] border border-[#262626] focus:border-[var(--accent)] outline-none text-[#e5e5e5] placeholder-[#525252] text-sm"
                                    placeholder="you@restaurant.com"
                                    required
                                />
                            </div>
                        ) : (
                            <div>
                                <label htmlFor="restaurant-name" className="block text-sm text-[#737373] mb-1.5">Restaurant</label>
                                <input
                                    id="restaurant-name"
                                    type="text"
                                    value={restaurantName}
                                    onChange={(e) => setRestaurantName(e.target.value)}
                                    className="w-full px-3 py-2.5 rounded-lg bg-[#0a0a0a] border border-[#262626] focus:border-[var(--accent)] outline-none text-[#e5e5e5] placeholder-[#525252] text-sm"
                                    placeholder="Vibanda Village"
                                    autoComplete="organization"
                                    required
                                />
                            </div>
                        )}

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
                                    autoComplete="current-password"
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
                            ) : isRegister ? (
                                "Create Account"
                            ) : (
                                <>Sign In <ArrowRight className="w-4 h-4" aria-hidden="true" /></>
                            )}
                        </button>
                    </form>

                    {showGeneralLoginOptions && <div className="mt-5 text-center space-y-2">
                        <button
                            onClick={() => {
                                setIsRegister(!isRegister);
                                setUseEmailLogin(false);
                                setError("");
                            }}
                            className="block w-full text-sm text-[#737373] hover:text-[var(--accent)]"
                        >
                            {isRegister
                                ? "Already have an account? Sign in"
                                : "New restaurant? Create account"}
                        </button>
                        {!isRegister && (
                            <button
                                type="button"
                                onClick={() => {
                                    setUseEmailLogin(!useEmailLogin);
                                    setError("");
                                }}
                                className="block w-full text-sm text-[#737373] hover:text-[var(--accent)]"
                            >
                                {useEmailLogin ? "Use restaurant sign in" : "Sign in with email instead"}
                            </button>
                        )}
                        {!isRegister && (
                            <a
                                href="/forgot-password"
                                className="block text-sm text-[#525252] hover:text-[var(--accent)]"
                            >
                                Forgot password?
                            </a>
                        )}
                    </div>}
                </div>

                <div className="mt-6 rounded-xl border border-[#342b1e] bg-[#1a1712] p-5">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#e8bd68]">Owner workspace</p>
                    <h3 className="mt-2 text-base font-semibold text-[#f2eee6]">A clearer view of your day.</h3>
                    <p className="mt-2 text-sm leading-6 text-[#b7b0a5]">Sign in to review your restaurant, find what needs attention, and plan your next move.</p>
                </div>
            </motion.div>
        </div>
    );
}
