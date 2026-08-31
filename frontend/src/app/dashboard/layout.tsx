"use client";

import { useAuth } from "@/context/AuthContext";
import { useRouter, usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import NotificationBell from "@/components/NotificationBell";
import RestaurantSwitcher from "@/components/RestaurantSwitcher";
import AttendanceWidget from "@/components/staff/AttendanceWidget";
import VerifyEmailBanner from "@/components/VerifyEmailBanner";
import QuickSwitchModal from "@/components/QuickSwitchModal";
import PinSetupModal from "@/components/PinSetupModal";
import PageLoader from "@/components/ui/PageLoader";
import SkipLink from "@/components/ui/SkipLink";
import { tierHome, StaffTier } from "@/lib/permissions";
import { labelForPath } from "@/lib/pathTitle";
import {
    Home,
    UtensilsCrossed,
    ShoppingBag,
    Package,
    CalendarDays,
    LayoutDashboard,
    LogOut,
    Repeat,
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
    type LucideIcon,
} from "lucide-react";

interface NavItem {
    href: string;
    label: string;
    icon: LucideIcon;
}

// Owner-only now: every staff_role tier has its own dedicated frontend under
// /staff/<tier> (see frontend/src/lib/permissions.ts and
// frontend/src/app/staff/*) — a staff account is redirected out of this
// dashboard entirely below, so there's no per-route access filtering left to
// maintain here (that hand-maintained `access` array is what caused the
// Manager nav-visibility bug this replaced).
//
// Grouped into labelled sections (the Stripe/Shopify-admin pattern) rather
// than one flat 15-item list — a flat list of 15 reads as a wall of equal
// links and forces visual scanning on every navigation.
const navSections: { label: string; items: NavItem[] }[] = [
    {
        label: "Home",
        items: [
            { href: "/dashboard", label: "Home", icon: Home },
        ],
    },
    {
        label: "Operate",
        items: [
            { href: "/dashboard/pos", label: "POS", icon: CreditCard },
            { href: "/dashboard/kitchen", label: "Kitchen", icon: ChefHat },
            { href: "/dashboard/orders", label: "Orders", icon: ShoppingBag },
            { href: "/dashboard/menu", label: "Menu", icon: UtensilsCrossed },
            { href: "/dashboard/inventory", label: "Stock", icon: Package },
            { href: "/dashboard/reservations", label: "Bookings", icon: CalendarDays },
            { href: "/dashboard/purchasing", label: "Purchasing", icon: Truck },
        ],
    },
    {
        label: "Insights",
        items: [
            // The Overview — one coherent business view (Today + Insights). The
            // module detail pages still live under /dashboard/ai/[module].
            { href: "/dashboard/ai", label: "Overview", icon: LayoutDashboard },
            { href: "/dashboard/sales", label: "Sales", icon: DollarSign },
            { href: "/dashboard/marketing", label: "Growth", icon: Megaphone },
            { href: "/dashboard/roi", label: "ROI", icon: Clock },
        ],
    },
    {
        label: "Manage",
        items: [
            { href: "/dashboard/staff", label: "Staff", icon: Users },
            { href: "/dashboard/ai-ops", label: "AI Ops", icon: Cpu },
            // Every staff tier can raise/view a support ticket from their own tier's
            // frontend too — the in-app channel that exists because Twilio (the
            // "call/WhatsApp the owner" fallback) is unfunded.
            { href: "/dashboard/support", label: "Support", icon: LifeBuoy },
        ],
    },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
    const { user, logout, isLoading } = useAuth();
    const router = useRouter();
    const pathname = usePathname();
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [showQuickSwitch, setShowQuickSwitch] = useState(false);
    const [showPinSetup, setShowPinSetup] = useState(false);

    // Owner/superadmin system accounts (role !== "staff") own this dashboard —
    // an Owner IS an ADMIN user (directive 015). Any role === "staff" account
    // belongs on its own tier's frontend under /staff/<tier>, never here.
    const isStaffAccount = (user?.role || "").toLowerCase() === "staff";
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

    // Tab title mirrors the sidebar's own label for the current section —
    // phone app-switchers and stacked tabs then say "POS · Chakula" etc.
    // Next.js re-asserts its route metadata title after hydration and on
    // client navigations, which can overwrite a plain assignment — so watch
    // the <title> element and re-apply ours whenever it gets reset while
    // this layout is mounted.
    useEffect(() => {
        const pairs = navSections.flatMap((s) => s.items.map((i) => ({ href: i.href, label: i.label })));
        const wanted = `${labelForPath(pathname, pairs)} · Chakula`;
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
    }, [pathname]);

    if (isLoading || (user && isStaffAccount && staffRole)) {
        return <PageLoader />;
    }

    if (!user) return null;

    const restaurantName = user?.restaurant_name || "Your Restaurant";

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
            <SkipLink />
            {/* Sidebar */}
            <aside
                className={`fixed inset-y-0 left-0 z-50 w-56 bg-[#0f0f0f] border-r border-[#1a1a1a] transform transition-transform duration-200 lg:translate-x-0 flex flex-col ${
                    sidebarOpen ? "translate-x-0" : "-translate-x-full"
                }`}
            >
                {/* Brand */}
                <div className="px-5 py-5 border-b border-[#1a1a1a] shrink-0">
                    <h1 className="text-lg font-bold text-[#e5e5e5] tracking-tight">Chakula</h1>
                    <p className="text-xs text-[var(--accent)] mt-0.5 truncate font-medium">{restaurantName}</p>
                    <p className="text-xs text-[#525252] truncate">{user.email}</p>
                </div>

                {/* Nav — scrollable so the grouped sections fit on short screens,
                    with the account block always visible below. */}
                <nav className="flex-1 overflow-y-auto p-3 pb-6 space-y-4" aria-label="Main navigation">
                    {navSections.map((section) => (
                        <div key={section.label}>
                            <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-[#525252]">
                                {section.label}
                            </p>
                            <div className="space-y-0.5">
                                {section.items.map((item) => {
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
                            </div>
                        </div>
                    ))}
                </nav>

                {/* Switch user / Logout */}
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

            {/* Mobile overlay */}
            {sidebarOpen && (
                <div
                    className="fixed inset-0 bg-black/60 z-40 lg:hidden"
                    onClick={() => setSidebarOpen(false)}
                />
            )}

            {/* Main */}
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
                        <RestaurantSwitcher />
                        <AttendanceWidget />
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
