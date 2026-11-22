"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { homeFor } from "@/lib/tenantHome";
import { PRODUCT_NAME, PRODUCT_TAGLINE } from "@/lib/brand";
import { useRouter } from "next/navigation";
import { Loader2, Eye, EyeOff, ArrowRight } from "lucide-react";
import { isLeviiiStoreClient } from "@/lib/nativeStore";

const AUTH_WAIT_MS = 6000;

export default function LoginPage() {
    const { user, isLoading, login, setInitialPassword, logout } = useAuth();
    const router = useRouter();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const [firstPassword, setFirstPassword] = useState(false);
    const [handoverCodeRequired, setHandoverCodeRequired] = useState(false);
    const [handoverCode, setHandoverCode] = useState("");
    const [nativeStore, setNativeStore] = useState(false);
    const [authStuck, setAuthStuck] = useState(false);

    useEffect(() => {
        setNativeStore(isLeviiiStoreClient());
    }, []);

    useEffect(() => {
        if (!isLoading) {
            setAuthStuck(false);
            return;
        }
        const t = window.setTimeout(() => setAuthStuck(true), AUTH_WAIT_MS);
        return () => window.clearTimeout(t);
    }, [isLoading]);

    useEffect(() => {
        if (isLoading) return;
        if (!user) return;
        const dest = homeFor(user.tenant_name, user.staff_role, user.role);
        if (isLeviiiStoreClient()) {
            window.location.replace(dest);
        } else {
            router.replace(dest);
        }
    }, [user, isLoading, router]);

    const handleSubmit = async (e?: React.FormEvent) => {
        e?.preventDefault();
        setError("");
        setLoading(true);
        try {
            const signedIn = firstPassword
                ? await setInitialPassword(email, password, handoverCodeRequired ? handoverCode : undefined)
                : await login(email, password);
            router.replace(homeFor(signedIn?.tenant_name, signedIn?.staff_role, signedIn?.role));
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
                    const needsCode =
                        typeof rawDetail === "object" &&
                        "handover_code_required" in rawDetail &&
                        Boolean((rawDetail as { handover_code_required?: boolean }).handover_code_required);
                    setHandoverCodeRequired(needsCode);
                    setError(
                        needsCode
                            ? "Enter the 6-digit handover code and choose a new password."
                            : "Choose your own password. This is your first sign-in.",
                    );
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

    if (user) {
        return <div className="min-h-dvh bg-[#0a0a0a]" role="status" aria-label="Opening home" />;
    }

    if (isLoading && !authStuck) {
        return (
            <div className="flex min-h-dvh items-center justify-center bg-[#0a0a0a] px-4">
                <Loader2 className="h-6 w-6 animate-spin text-[#e8bd68]" aria-label="Checking sign-in" />
            </div>
        );
    }

    return (
        <div className="min-h-dvh overflow-y-auto overscroll-y-contain bg-[#0a0a0a] px-4 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-[max(1.5rem,env(safe-area-inset-top))]">
            <div className="mx-auto w-full max-w-sm">
                <div className="mb-8 text-center">
                    <h1 className="text-3xl font-bold tracking-tight text-[#e5e5e5]">
                        {PRODUCT_NAME}
                    </h1>
                    <p className="mt-1 text-sm text-[#737373]">{PRODUCT_TAGLINE}</p>
                </div>

                <div className="rounded-xl border border-[#262626] bg-[#141414] p-6">
                    <h2 className="mb-5 text-lg font-semibold text-[#e5e5e5]">
                        {firstPassword ? "Set your password" : "Sign in"}
                    </h2>

                    {error && (
                        <div className="mb-4 rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-sm text-red-400">
                            {error}
                        </div>
                    )}

                    {authStuck && isLoading && (
                        <div className="mb-4 rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-sm text-amber-200">
                            Sign-in is taking longer than expected. You can clear this device and try again.
                            <button
                                type="button"
                                className="mt-3 flex min-h-11 w-full items-center justify-center rounded-lg border border-amber-400/40 px-3 font-semibold text-amber-100"
                                onClick={() => {
                                    logout();
                                    setAuthStuck(false);
                                }}
                            >
                                Sign out and try again
                            </button>
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div>
                            <label htmlFor="email" className="mb-1.5 block text-sm text-[#737373]">Email</label>
                            <input
                                id="email"
                                name="username"
                                type="email"
                                inputMode="email"
                                autoComplete="username"
                                autoCapitalize="none"
                                autoCorrect="off"
                                spellCheck={false}
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="w-full rounded-lg border border-[#262626] bg-[#0a0a0a] px-3 py-2.5 text-sm text-[#e5e5e5] outline-none placeholder-[#525252] focus:border-[var(--accent)]"
                                placeholder={nativeStore ? "jack@eleven.leviii" : "you@eleven.leviii"}
                                required
                            />
                        </div>

                        {handoverCodeRequired && (
                            <div>
                                <label htmlFor="handover" className="mb-1.5 block text-sm text-[#737373]">Handover code (6 digits)</label>
                                <input
                                    id="handover"
                                    type="text"
                                    inputMode="numeric"
                                    pattern="[0-9]{6}"
                                    maxLength={6}
                                    autoComplete="one-time-code"
                                    enterKeyHint="next"
                                    value={handoverCode}
                                    onChange={(e) => setHandoverCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                                    className="w-full rounded-lg border border-[#262626] bg-[#0a0a0a] px-3 py-2.5 text-sm tracking-widest text-[#e5e5e5] outline-none placeholder-[#525252] focus:border-[var(--accent)]"
                                    placeholder="123456"
                                    required
                                />
                            </div>
                        )}

                        <div>
                            <label htmlFor="password" className="mb-1.5 block text-sm text-[#737373]">
                                {firstPassword ? "New password" : "Password"}
                            </label>
                            <div className="relative">
                                <input
                                    id="password"
                                    name="password"
                                    type={showPassword ? "text" : "password"}
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter") {
                                            e.preventDefault();
                                            void handleSubmit();
                                        }
                                    }}
                                    enterKeyHint="go"
                                    className="w-full rounded-lg border border-[#262626] bg-[#0a0a0a] py-2.5 pl-3 pr-10 text-sm text-[#e5e5e5] outline-none placeholder-[#525252] focus:border-[var(--accent)]"
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
                                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                </button>
                            </div>
                        </div>

                        <button
                            type="submit"
                            disabled={loading}
                            className="flex min-h-11 w-full items-center justify-center gap-2 rounded-lg bg-[#e8bd68] py-2.5 text-sm font-semibold text-[#17120a] transition-colors hover:bg-[#f3cf84] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#e8bd68] disabled:cursor-not-allowed disabled:opacity-50"
                        >
                            {loading ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                            ) : firstPassword ? (
                                "Set password and sign in"
                            ) : (
                                <>Sign in <ArrowRight className="h-4 w-4" aria-hidden="true" /></>
                            )}
                        </button>
                    </form>
                </div>
            </div>
        </div>
    );
}