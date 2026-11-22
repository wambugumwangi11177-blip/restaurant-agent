"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { homeFor } from "@/lib/tenantHome";
import { isLeviiiStoreClient } from "@/lib/nativeStore";

export default function HomePage() {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading) {
      if (user) {
        const dest = homeFor(user.tenant_name, user.staff_role, user.role);
        if (isLeviiiStoreClient()) {
          window.location.replace(dest);
        } else {
          router.push(dest);
        }
      } else if (isLeviiiStoreClient()) {
        window.location.replace("/login");
      } else {
        router.push("/login");
      }
    }
  }, [user, isLoading, router]);

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-5 h-5 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
    </div>
  );
}
