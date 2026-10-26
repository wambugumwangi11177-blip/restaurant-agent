"use client";
import {useDailyReview} from "@/lib/owner/useDailyReview";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { ArrowUpRight, BarChart3, BookOpen, ChefHat, ClipboardPen, FileText, Home, MessageCircle, Settings2, Sparkles } from "lucide-react";
import NotificationBell from "@/components/NotificationBell";
import BranchPicker from "@/components/owner/BranchPicker";
import SettingsProvider from "@/components/owner/settings/SettingsProvider";
import { useAuth } from "@/context/AuthContext";
import { nairobiDate } from "@/lib/owner/format";
import { tenantConfig } from "@/lib/tenantConfig";
import { homeFor, isOwnerAccount, OWNER_HOME } from "@/lib/tenantHome";

export const TABS = [
  { href: OWNER_HOME, label: "Home", icon: Home },
  { href: "/os", label: "Ask LEVIII", icon: MessageCircle },
  { href: "/reports", label: "Reports", icon: FileText },
] as const;
const WORK = [
  { href: "/daily", label: "Daily work", icon: ClipboardPen },
  { href: "/explore", label: "All tools", icon: BookOpen },
  { href: "/planning", label: "Plan & improve", icon: ChefHat, note: "Stock, recipes & prices" },
  { href: "/entries", label: "Team entries", icon: ClipboardPen, note: "Record the day" },
];
export default function OwnerShell({ children }: { children: React.ReactNode }) {
  const reviewDay=useDailyReview();
  const pathname = usePathname(); const router = useRouter(); const { user, isLoading } = useAuth();
  const owner = isOwnerAccount(user);
  useEffect(() => { if (isLoading) return; if (!user) router.replace("/login"); else if (!owner) router.replace(homeFor(user)); }, [user, isLoading, owner, router]);
  if (isLoading || !owner) return <p role="status" className="p-6">Checking account access…</p>;
  const config = tenantConfig(user?.tenant_name);
  const active = (href: string) => pathname === href || (href !== OWNER_HOME && pathname.startsWith(`${href}/`));
  const links = [...TABS, ...WORK, ...(config.operations ? [{ href: "/dashboard", label: "Operations", icon: Settings2 }] : [])];
  return <div className="vibanda-theme owner-theme leviii-app min-h-screen">
    <aside className="leviii-sidebar print:hidden">
      <Link href="/home" aria-label="LEVIII home" className="leviii-brand"><span className="leviii-mark">L<span>✳</span></span><span>LEVIII<small>YOUR RESTAURANT PARTNER</small></span></Link>
      <p className="leviii-nav-label">YOUR WORKSPACE</p>
      <nav aria-label="Owner pages" className="space-y-1">{links.map(({ href, label, icon: Icon }) => <Link key={href} href={href} aria-current={active(href) ? "page" : undefined} className={`leviii-nav-link ${active(href) ? "is-active" : ""}`}><Icon size={19} strokeWidth={1.7} />{label}{active(href) && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-current" />}</Link>)}</nav>
      <div className="leviii-side-note"><Sparkles size={20} /><p>A little clarity.<br /><strong>A better restaurant.</strong></p><span>One set of records. Every decision connected.</span><Link href="/os">Think it through with LEVIII <ArrowUpRight size={14} /></Link></div>
      <div className="leviii-account"><span>{(user?.restaurant_name || "R").slice(0, 1)}</span><div><b>{user?.restaurant_name || "Your restaurant"}</b><small>Owner workspace</small></div></div>
    </aside>
    <div className="leviii-main">
      <header className="leviii-topbar print:hidden"><div className="min-w-0"><span className="leviii-mobile-brand">LEVIII</span><p>{nairobiDate()} <span className="hidden sm:inline">· Nairobi</span></p></div><div className="flex min-w-0 items-center gap-3"><BranchPicker /><NotificationBell ownerHome={OWNER_HOME} /></div></header>
      <main className="leviii-content"><SettingsProvider>
        {config.banner && <div className="leviii-demo-notice"><span className="leviii-status-dot" /><p><b>Demo workspace</b><span> · Generated restaurant records. Explore every tool before connecting your own data.</span></p><BookOpen size={15} aria-hidden /></div>}
        {pathname!==OWNER_HOME&&<p className="mb-4 text-xs text-[var(--v-muted-foreground)]" aria-label="Daily review date">Daily review · {reviewDay} · Nairobi. Analysis periods and source dates are shown with each result.</p>}
        {children}
      </SettingsProvider></main>
      <footer className="leviii-footer print:hidden"><span>LEVIII <span className="mx-2">/</span> A clearer view of your restaurant</span><span className="inline-flex items-center gap-1"><BarChart3 size={13} /> Worked out from your records</span></footer>
    </div>
    <nav aria-label="Mobile owner pages" className="leviii-bottom-nav print:hidden">{[...TABS, { href: "/planning", label: "Plan", icon: ChefHat }, { href: "/entries", label: "Entries", icon: ClipboardPen }].map(({href,label,icon:Icon})=><Link key={href} href={href} aria-current={active(href)?"page":undefined} className={active(href)?"is-active":""}><Icon size={19}/><span>{label}</span></Link>)}</nav>
  </div>;
}
