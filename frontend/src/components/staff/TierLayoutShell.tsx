"use client";

import { useAuth } from "@/context/AuthContext";
import { useRouter, usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import NotificationBell from "@/components/NotificationBell";
import AttendanceWidget from "@/components/staff/AttendanceWidget";
import QuickSwitchModal from "@/components/QuickSwitchModal";
import PinSetupModal from "@/components/PinSetupModal";
import PageLoader from "@/components/ui/PageLoader";
import SkipLink from "@/components/ui/SkipLink";
import { LogOut, Repeat, Menu as MenuIcon, X, type LucideIcon } from "lucide-react";
import { tierHome, StaffTier } from "@/lib/permissions";
import { labelForPath } from "@/lib/pathTitle";

export interface TierNavItem {
    href: string;
    label: string;
    icon: LucideIcon;
}

/**
 * Thin, tier-specific nav shell shared by every /staff/<tier>/layout.tsx.
 * Unlike the old dashboard/layout.tsx, there's no `access` array to filter —
 * each tier's layout only ever passes the nav items that tier is entitled to
 * (see frontend/src/lib/permissions.ts), so there's nothing to hide. This
 * file just enforces that the logged-in staff_role actually matches the tier
 * this route tree belongs to (an Owner impersonating, or a role reassignment
 * mid-session, could otherwise land someone on the wrong tier's UI).
 */
export default function TierLayoutShell({
    tier,
    tierLabel,
    navItems,
    children,
}: {
    tier: Exclude<StaffTier, "owner">;
    tierLabel: string;
    navItems: TierNavItem[];
    children: React.ReactNode;
}) {
    const { user, logout } = useAuth();
    const router = useRouter();
    const pathname = usePathname();
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [showQuickSwitch, setShowQuickSwitch] = useState(false);
    const [showPinSetup, setShowPinSetup] = useState(false);

    const staffRole = user?.staff_role || null;

    useEffect(() => {
        if (staffRole && staffRole !== tier) {
            router.push(tierHome(staffRole as StaffTier));
        }
    }, [staffRole, tier, router]);

    useEffect(() => {
        if (!sidebarOpen) return;
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") setSidebarOpen(false);
        };
        document.addEventListener("keydown", handleKeyDown);
        return () => document.removeEventListener("keydown", handleKeyDown);
    }, [sidebarOpen]);

    // Tab title mirrors the sidebar's own label for the current section —
    // same single-source-of-truth pattern as the owner dashboard layout,
    // with the same MutationObserver guard against Next.js re-asserting its
    // route metadata title after hydration.
    useEffect(() => {
        const wanted = `${labelForPath(pathname, navItems.map((i) => ({ href: i.href, label: i.label })))} · Chakula`;
        const apply = () => { document.title = wanted; };
        apply();
        const titleEl = document.querySelector("title");
        let observer: MutationObserver | null = null;
        if (titleEl) {
            observer = new MutationObserver(() => {
                if (document.title !== wanted) apply();
            });
            observer.observe(titleEl, { childList: true, characterData: true, subtree: true });
        }
        return () => observer?.disconnect();
    }, [pathname, navItems]);

    if (!user || staffRole !== tier) {
        // Still resolving auth, or a role/tier mismatch mid-redirect: the
        // spinner, never a blank screen — a blank flash reads as "broken".
        // (A fully logged-out or non-staff visitor is redirected by the
        // parent /staff/layout.tsx before this branch is reached.)
        return <PageLoader />;
    }

    const restaurantName = user?.restaurant_name || "Your Restaurant";

    return (
        <div className="min-h-screen flex">
            <SkipLink />
            <aside
                className={`fixed inset-y-0 left-0 z-50 w-56 bg-[#0f0f0f] border-r border-[#1a1a1a] transform transition-transform duration-200 lg:translate-x-0 flex flex-col ${
                    sidebarOpen ? "translate-x-0" : "-translate-x-full"
                }`}
            >
                <div className="px-5 py-5 border-b border-[#1a1a1a] shrink-0">
                    <h1 className="text-lg font-bold text-[#e5e5e5] tracking-tight">Chakula</h1>
                    <p className="text-xs text-[var(--accent)] mt-0.5 truncate font-medium">{restaurantName}</p>
                    <p className="text-xs text-[#525252] truncate">{tierLabel}</p>
                </div>

                <nav className="flex-1 overflow-y-auto p-3 pb-6 space-y-0.5" aria-label="Main navigation">
                    {navItems.map((item) => {
                        const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                onClick={() => setSidebarOpen(false)}
                                aria-current={isActive ? "page" : undefined}
                                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                                    isActive
                                        ? "bg-[#1a1a1a] text-[var(--accent)]"
                                        : "text-[#737373] hover:text-[#e5e5e5] hover:bg-[#141414]"
                                }`}
                            >
                                <item.icon className="w-4 h-4" />
                                <span className="font-medium">{item.label}</span>
                            </Link>
                        );
                    })}
                </nav>

                <div className="shrink-0 p-3 border-t border-[#1a1a1a] space-y-0.5">
                    <button
                        onClick={() => setShowQuickSwitch(true)}
                        className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-[#737373] hover:text-[var(--accent)] hover:bg-[#141414] w-full transition-colors"
                    >
                        <Repeat className="w-4 h-4" />
                        <span className="font-medium">Switch user</span>
                    </button>
                    <button
                        onClick={() => { logout(); router.push("/login"); }}
                        className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-[#737373] hover:text-red-400 hover:bg-red-500/5 w-full transition-colors"
                    >
                        <LogOut className="w-4 h-4" />
                        <span className="font-medium">Logout</span>
                    </button>
                </div>
            </aside>

            {showQuickSwitch && (
                <QuickSwitchModal
                    onClose={() => setShowQuickSwitch(false)}
                    onSetUpOwnPin={() => { setShowQuickSwitch(false); setShowPinSetup(true); }}
                />
            )}
            {showPinSetup && <PinSetupModal onClose={() => setShowPinSetup(false)} />}

            {sidebarOpen && (
                <button
                    type="button"
                    aria-label="Close sidebar"
                    className="fixed inset-0 bg-black/60 z-40 lg:hidden appearance-none cursor-default"
                    onClick={() => setSidebarOpen(false)}
                />
            )}

            <main id="main-content" tabIndex={-1} className="flex-1 lg:ml-56 min-h-screen focus:outline-none">
                <header className="sticky top-0 z-30 bg-[#0a0a0a]/90 backdrop-blur-sm border-b border-[#1a1a1a] px-5 py-3 flex items-center justify-between">
                    <button
                        onClick={() => setSidebarOpen(!sidebarOpen)}
                        aria-label={sidebarOpen ? "Close menu" : "Open menu"}
                        className="lg:hidden text-[#737373] hover:text-[#e5e5e5]"
                    >
                        {sidebarOpen ? <X className="w-5 h-5" /> : <MenuIcon className="w-5 h-5" />}
                    </button>
                    <div className="flex items-center gap-4">
                        <AttendanceWidget />
                        <NotificationBell />
                        <div className="text-xs text-[#525252]">{tierLabel}</div>
                    </div>
                </header>

                <div className="p-5 max-w-6xl">{children}</div>
            </main>
        </div>
    );
}
