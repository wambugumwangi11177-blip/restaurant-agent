"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";

export default function SuperLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) return;
    if (!user || user.role !== "superadmin") {
      router.replace("/login");
    }
  }, [user, isLoading, router]);

  if (isLoading || !user || user.role !== "superadmin") {
    return <div className="min-h-dvh bg-[#0a0a0a]" />;
  }

  return (
    <div className="min-h-dvh bg-[#0a0a0a] text-zinc-100">
      <header className="border-b border-white/10 px-4 py-4">
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">LEVIII</p>
        <h1 className="text-lg font-semibold">Clients</h1>
      </header>
      <main className="mx-auto max-w-lg px-4 py-6">{children}</main>
    </div>
  );
}