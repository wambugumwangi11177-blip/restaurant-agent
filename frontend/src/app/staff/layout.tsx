"use client";

import { useAuth } from "@/context/AuthContext";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { tierHome, StaffTier } from "@/lib/permissions";

/**
 * Root guard for every tier-specific frontend under /staff/<tier>/*.
 * Each tier's own layout.tsx (e.g. staff/kitchen/layout.tsx) owns its nav and
 * further restricts which sub-routes that tier can see — this file only
 * handles the three cross-cutting cases: not logged in, an Owner/Admin
 * account (which belongs on /dashboard, not here), and a staff account with
 * no staff_role assigned yet.
 */
export default function StaffRootLayout({ children }: { children: React.ReactNode }) {
    const { user, logout, isLoading } = useAuth();
    const router = useRouter();

    const isStaffAccount = ((user as any)?.role || "").toLowerCase() === "staff";
    const staffRole = (user?.staff_role || null) as StaffTier | null;
    const roleUnassigned = isStaffAccount && !staffRole;

    useEffect(() => {
        if (isLoading) return;
        if (!user) {
            router.push("/login");
            return;
        }
        // Owner/Manager-tier system accounts (role !== "staff") own /dashboard,
        // not this tree — send them back rather than showing a dead end.
        if (!isStaffAccount) {
            router.push("/dashboard");
        }
    }, [user, isLoading, isStaffAccount, router]);

    if (isLoading || !user || !isStaffAccount) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <div className="w-6 h-6 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
            </div>
        );
    }

    if (roleUnassigned) {
        return (
            <div className="min-h-screen flex items-center justify-center px-6">
                <div className="max-w-sm text-center space-y-3">
                    <h1 className="text-lg font-semibold text-[#e5e5e5]">Role not assigned yet</h1>
                    <p className="text-sm text-[#737373]">
                        Your account ({user.email}) doesn&apos;t have a role assigned, so there&apos;s
                        nothing to show yet. Ask your manager or owner to assign one from Staff settings.
                    </p>
                    <button
                        onClick={() => { logout(); router.push("/login"); }}
                        className="text-sm text-[var(--accent)] hover:underline"
                    >
                        Log out
                    </button>
                </div>
            </div>
        );
    }

    return <>{children}</>;
}
