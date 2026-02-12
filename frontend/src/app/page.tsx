"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { Brain, Loader2 } from "lucide-react";

export default function HomePage() {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading) {
      if (user) {
        router.push("/dashboard");
      } else {
        router.push("/login");
      }
    }
  }, [user, isLoading, router]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-4">
      <Brain className="w-12 h-12 text-indigo-400 animate-pulse" />
      <Loader2 className="w-6 h-6 text-gray-500 animate-spin" />
    </div>
  );
}
