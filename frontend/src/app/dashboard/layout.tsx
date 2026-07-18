"use client";

import { useAuth } from "@/context/AuthContext";
import { useRouter, usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import NotificationBell from "@/components/NotificationBell";
import VerifyEmailBanner from "@/components/VerifyEmailBanner";
import { tierHome, StaffTier } from "@/lib/permissions";
import {
    Home,
    UtensilsCrossed,
    ShoppingBag,
    Package,
    CalendarDays,
    Brain,
    LogOut,
    Menu as MenuIcon,
    X,
    CreditCard,
    ChefHat,
    DollarSign,
    Clock,
    Megaphone,
    Cpu,
    Users,
    Truck,
    LifeBuoy,
} from "lucide-react";

// Owner-only now: every staff_role tier has its own dedicated frontend under
// /staff/<tier> (see frontend/src/lib/permissions.ts and
// frontend/src/app/staff/*) — a staff account is redirected out of this
// dashboard entirely below, so there's no per-route access filtering left to
// maintain here (that hand-maintained `access` array is what caused the
// Manager nav-visibility bug this replaced).
const navItems = [
    { href: "/dashboard", label: "Home", icon: Home },
    { href: "/dashboard/pos", label: "POS", icon: CreditCard },
    { href: "/dashboard/kitchen", label: "Kitchen", icon: ChefHat },
    { href: "/dashboard/orders", label: "Orders", icon: ShoppingBag },
    { href: "/dashboard/menu", label: "Menu", icon: UtensilsCrossed },
    { href: "/dashboard/inventory", label: "Stock", icon: Package },
    { href: "/dashboard/reservations", label: "Bookings", icon: CalendarDays },
    { href: "/dashboard/sales", label: "Sales", icon: DollarSign },
    // The AI Command Center. Superseded /dashboard/insights, which served a
    // hardcoded Lavy demo and was deleted 2026-07-08.
    { href: "/dashboard/ai", label: "AI", icon: Brain },
    { href: "/dashboard/marketing", label: "Growth", icon: Megaphone },
    { href: "/dashboard/staff", label: "Staff", icon: Users },
    { href: "/dashboard/purchasing", label: "Purchasing", icon: Truck },
    { href: "/dashboard/roi", label: "ROI", icon: Clock },
    { href: "/dashboard/ai-ops", label: "AI Ops", icon: Cpu },
    // Every staff tier can raise/view a support ticket from their own tier's
    // frontend too — the in-app channel that exists because Twilio (the
    // "call/WhatsApp the owner" fallback) is unfunded.
    { href: "/dashboard/support", label: "Support", icon: LifeBuoy },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
    const { user, logout, isLoading } = useAuth();
    const router = useRouter();
    const pathname = usePathname();
    const [sidebarOpen, setSidebarOpen] = useState(false);

    // Owner/superadmin system accounts (role !== "staff") own this dashboard —
    // an Owner IS an ADMIN user (directive 015). Any role === "staff" account
    // belongs on its own tier's frontend under /staff/<tier>, never here.
    const isStaffAccount = ((user as any)?.role || "").toLowerCase() === "staff";
    const staffRole = (user?.staff_role || null) as StaffTier | null;
    const roleUnassigned = isStaffAccount && !staffRole;

    useEffect(() => {
        if (isLoading) return;
        if (!user) {
            router.push("/login");
            return;
        }
        if (isStaffAccount && staffRole) {
            router.push(tierHome(staffRole));
        }
    }, [user, isLoading, isStaffAccount, staffRole, router]);

    if (isLoading || (user && isStaffAccount && staffRole)) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <div className="w-6 h-6 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
            </div>
        );
    }

    if (!user) return null;

    const restaurantName = (user as any).restaurant_name || "Your Restaurant";

    // Directive 015's Edge Cases: don't guess a tier for an unassigned staff
    // account — surface it plainly instead of a confusing empty nav / string
    // of 403s. Distinguishable from "logged out" so the person knows exactly
    // what to do next (ask their manager), not that something is broken.
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

    return (
        <div className="min-h-screen flex">
            {/* Sidebar */}
            <aside
                className={`fixed inset-y-0 left-0 z-50 w-56 bg-[#0f0f0f] border-r border-[#1a1a1a] transform transition-transform duration-200 lg:translate-x-0 ${
                    sidebarOpen ? "translate-x-0" : "-translate-x-full"
                }`}
            >
                {/* Brand */}
                <div className="px-5 py-5 border-b border-[#1a1a1a]">
                    <h1 className="text-lg font-bold text-[#e5e5e5] tracking-tight">Chakula</h1>
                    <p className="text-xs text-[var(--accent)] mt-0.5 truncate font-medium">{restaurantName}</p>
                    <p className="text-xs text-[#525252] truncate">{user.email}</p>
                </div>

                {/* Nav */}
                <nav className="p-3 space-y-0.5">
                    {navItems.map((item) => {
                        const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                onClick={() => setSidebarOpen(false)}
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

                {/* Logout */}
                <div className="absolute bottom-0 left-0 right-0 p-3 border-t border-[#1a1a1a]">
                    <button
                        onClick={() => { logout(); router.push("/login"); }}
                        className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-[#737373] hover:text-red-400 hover:bg-red-500/5 w-full transition-colors"
                    >
                        <LogOut className="w-4 h-4" />
                        <span className="font-medium">Logout</span>
                    </button>
                </div>
            </aside>

            {/* Mobile overlay */}
            {sidebarOpen && (
                <div
                    className="fixed inset-0 bg-black/60 z-40 lg:hidden"
                    onClick={() => setSidebarOpen(false)}
                />
            )}

            {/* Main */}
            <main className="flex-1 lg:ml-56 min-h-screen">
                <header className="sticky top-0 z-30 bg-[#0a0a0a]/90 backdrop-blur-sm border-b border-[#1a1a1a] px-5 py-3 flex items-center justify-between">
                    <button
                        onClick={() => setSidebarOpen(!sidebarOpen)}
                        aria-label={sidebarOpen ? "Close menu" : "Open menu"}
                        className="lg:hidden text-[#737373] hover:text-[#e5e5e5]"
                    >
                        {sidebarOpen ? <X className="w-5 h-5" /> : <MenuIcon className="w-5 h-5" />}
                    </button>
                    <div className="flex items-center gap-4">
                        <NotificationBell />
                        <div className="text-xs text-[#525252]">{user.role}</div>
                    </div>
                </header>

                <VerifyEmailBanner />

                <div className="p-5 max-w-6xl">
                    {children}
                </div>
            </main>
        </div>
    );
}
