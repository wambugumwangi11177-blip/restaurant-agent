"use client";

import { useAuth } from "@/context/AuthContext";
import { isEleven } from "@/lib/tenantHome";
import { tierHome, type StaffTier } from "@/lib/permissions";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function ElevenLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();
  const owner = user?.role === "admin" || user?.role === "superadmin";
  const allowed = owner && isEleven(user?.tenant_name);

  useEffect(() => {
    if (isLoading) return;
    if (!user) router.replace("/login");
    else if (!owner) router.replace(tierHome(user.staff_role as StaffTier | null));
    else if (!allowed) router.replace("/dashboard");
  }, [user, isLoading, owner, allowed, router]);

  if (isLoading || !allowed) {
    return (
      <p role="status" className="owner-glass-theme p-6 text-zinc-300">
        Checking account access…
      </p>
    );
  }
  return children;
}
