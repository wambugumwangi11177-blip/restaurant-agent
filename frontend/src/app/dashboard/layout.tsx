"use client";

import { useAuth } from "@/context/AuthContext";
import { useRouter, usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import NotificationBell from "@/components/NotificationBell";
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

// Directive 015's permission matrix, by nav route. `access` lists the
// staff_role tiers that can see this route at all (R or RW — the backend is
// what actually distinguishes read-only from mutate, per route; this list is
// purely "show the nav entry or don't"). Owner and Manager-tier ADMIN/
// SUPERADMIN accounts (role !== "staff") always see everything — see
// `visible()` below — so they're intentionally omitted from every list.
const navItems = [
    { href: "/dashboard",              label: "Home",     icon: Home,          access: ["manager", "controller"] },
    { href: "/dashboard/pos",          label: "POS",      icon: CreditCard,    access: ["supervisor", "waiter"] },
    { href: "/dashboard/kitchen",      label: "Kitchen",  icon: ChefHat,       access: ["supervisor", "kitchen"] },
    { href: "/dashboard/orders",       label: "Orders",   icon: ShoppingBag,   access: ["supervisor", "controller", "kitchen", "waiter"] },
    { href: "/dashboard/menu",         label: "Menu",     icon: UtensilsCrossed, access: ["supervisor", "kitchen", "waiter"] },
    { href: "/dashboard/inventory",    label: "Stock",    icon: Package,       access: ["controller", "stockkeeper", "kitchen"] },
    { href: "/dashboard/reservations", label: "Bookings", icon: CalendarDays,  access: ["supervisor", "waiter"] },
    { href: "/dashboard/sales",        label: "Sales",    icon: DollarSign,    access: ["supervisor", "controller"] },
    // The AI Command Center. Superseded /dashboard/insights, which served a
    // hardcoded Lavy demo and was deleted 2026-07-08.
    { href: "/dashboard/ai",           label: "AI",       icon: Brain,         access: ["manager", "controller"] },
    { href: "/dashboard/marketing",    label: "Growth",   icon: Megaphone,     access: ["manager"] },
    // routers/staff.py gates this to Owner/Manager only (require_staff_role(MANAGER)).
    { href: "/dashboard/staff",        label: "Staff",    icon: Users,         access: ["manager"] },
    // Backend (routers/purchase_orders.py, suppliers.py) further splits
    // read/approve/receive by role — this just governs who sees the nav
    // entry at all: Manager/Controller read, Supervisor approves, Stockkeeper receives.
    { href: "/dashboard/purchasing",   label: "Purchasing", icon: Truck,       access: ["manager", "controller", "supervisor", "stockkeeper"] },
    { href: "/dashboard/roi",          label: "ROI",      icon: Clock,         access: ["manager", "controller"] },
    // AI Ops shows this restaurant's OWN AI cost/reliability (reads /ai/usage) —
    // same access group as the rest of /ai/*.
    { href: "/dashboard/ai-ops",       label: "AI Ops",   icon: Cpu,           access: ["manager", "controller"] },
    // Every staff tier can raise/view a support ticket — the in-app channel
    // that exists because Twilio (the "call/WhatsApp the owner" fallback) is
    // unfunded. routers/support.py further scopes list_tickets to "own
    // tickets only" for non-Owner/Manager; this just governs nav visibility.
    { href: "/dashboard/support",      label: "Support",  icon: LifeBuoy,      access: ["manager", "supervisor", "controller", "stockkeeper", "kitchen", "waiter"] },
];

// Per-tier landing page when a staff_role account hits a route it can't see
// (or "/dashboard" itself, which only Manager/Controller can see). Falls
// back to the first nav entry that tier can reach if it isn't listed here.
const TIER_HOME: Record<string, string> = {
    waiter: "/dashboard/pos",
    kitchen: "/dashboard/kitchen",
    stockkeeper: "/dashboard/inventory",
    supervisor: "/dashboard/pos",
    controller: "/dashboard/sales",
};

function isRouteAllowed(href: string, staffRole: string | null): boolean {
    const item = navItems.find((i) => i.href === href);
    if (!item) return true;   // Not a matrix-governed route — don't block navigation to it here.
    return !!staffRole && item.access.includes(staffRole);
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
    const { user, logout, isLoading } = useAuth();
    const router = useRouter();
    const pathname = usePathname();
    const [sidebarOpen, setSidebarOpen] = useState(false);

    // Owner/Manager-tier system accounts (role === "admin"/"superadmin") pass
    // through every check below — an Owner IS an ADMIN user (directive 015),
    // never gated by staff_role. Only role === "staff" accounts are subject
    // to the matrix at all.
    const isStaffAccount = ((user as any)?.role || "").toLowerCase() === "staff";
    const staffRole: string | null = (user as any)?.staff_role || null;
    const roleUnassigned = isStaffAccount && !staffRole;

    const visibleNavItems = navItems.filter(
        (item) => !isStaffAccount || isRouteAllowed(item.href, staffRole)
    );

    useEffect(() => {
        if (!isLoading && !user) {
            router.push("/login");
            return;
        }
        if (!isLoading && user && isStaffAccount && staffRole && !roleUnassigned) {
            const onDisallowedPage = navItems.some(
                (i) =>
                    !isRouteAllowed(i.href, staffRole) &&
                    // Match "/dashboard" exactly, never as a prefix, or it would
                    // swallow every /dashboard/* path (incl. POS).
                    (pathname === i.href ||
                        (i.href !== "/dashboard" && pathname.startsWith(i.href + "/")))
            );
            if (onDisallowedPage) {
                const fallback = TIER_HOME[staffRole] || visibleNavItems[0]?.href || "/dashboard/pos";
                router.push(fallback);
            }
        }
    }, [user, isLoading, isStaffAccount, staffRole, roleUnassigned, pathname, router]);

    if (isLoading) {
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
                    {visibleNavItems.map((item) => {
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

                <div className="p-5 max-w-6xl">
                    {children}
                </div>
            </main>
        </div>
    );
}
