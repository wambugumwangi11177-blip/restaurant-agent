"use client";
/**
 * The one owner shell (docs/v2/SPEC.md §2 principle 5): Home · Ask LEVIII · Reports for the owner of every tenant, configured by
 * tenantConfig (name, where the figures come from, a standing banner). Bottom bar on a phone, tabs on a desk.
 * An owner of a restaurant that has the operational screens gets a way to them; managers and staff never come here.
 */
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { FileText, Home, MessageCircle, Settings2 } from "lucide-react";
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

export default function OwnerShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, isLoading } = useAuth();
  const owner = isOwnerAccount(user);
  useEffect(() => {
    if (isLoading) return;
    if (!user) router.replace("/login");
    else if (!owner) router.replace(homeFor(user));
  }, [user, isLoading, owner, router]);
  if (isLoading || !owner) return <p role="status" className="p-6">Checking account access…</p>;

  const config = tenantConfig(user?.tenant_name);
  const tabs = config.operations ? [...TABS, { href: "/dashboard", label: "Operations", icon: Settings2 }] : TABS;
  const isActive = (href: string) => (href === OWNER_HOME ? pathname === href : pathname === href || pathname.startsWith(`${href}/`));

  return (
    <div className="vibanda-theme owner-theme min-h-screen pb-20 md:pb-0">
      <header className="px-4 pt-6 pb-2 md:px-8">
        <div className="float-right print:hidden"><NotificationBell ownerHome={OWNER_HOME} /></div>
        <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--v-muted-foreground)]">{nairobiDate()} · Nairobi</p>
        {config.banner && (
          <p className="mb-2 inline-flex max-w-full rounded-full border border-[hsl(43_76%_57_/.45)] bg-[hsl(43_76%_57_/.12)] px-3 py-1 text-[11px] text-[var(--v-muted-foreground)]">{config.banner}</p>
        )}
        <div><BranchPicker /></div>
        <div className="flex flex-wrap gap-4 text-sm print:hidden"><Link className="inline-flex min-h-11 items-center underline" href="/entries">Team entries</Link><Link className="inline-flex min-h-11 items-center underline" href="/planning">Kitchen & money tools</Link></div>
        <nav aria-label="Owner pages" className="mt-3 hidden gap-1 md:flex print:hidden">
          {tabs.map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href} aria-current={isActive(href) ? "page" : undefined}
              className={`flex items-center gap-2 rounded-lg px-3 py-2.5 text-[12px] font-medium ${
                isActive(href) ? "bg-[var(--v-primary)] text-[var(--v-primary-foreground)]" : "text-[var(--v-muted-foreground)] hover:bg-[var(--v-muted)] hover:text-[var(--v-foreground)]"
              }`}>
              <Icon size={16} /> {label}
            </Link>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-[1180px] px-4 pb-16 pt-4 sm:px-7 lg:px-10"><SettingsProvider>{children}</SettingsProvider></main>
      <nav aria-label="Owner pages" className="fixed inset-x-0 bottom-0 grid border-t border-[var(--v-border)] bg-[var(--v-card)] md:hidden print:hidden"
        style={{ gridTemplateColumns: `repeat(${tabs.length}, minmax(0, 1fr))` }}>
        {tabs.map(({ href, label, icon: Icon }) => (
          <Link key={href} href={href} aria-current={isActive(href) ? "page" : undefined}
            className={`flex min-h-14 flex-col items-center justify-center gap-1 py-2 text-xs ${isActive(href) ? "text-[var(--v-primary)]" : "text-[var(--v-muted-foreground)]"}`}>
            <Icon size={20} /> {label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
