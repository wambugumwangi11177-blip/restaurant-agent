"use client";

import StoreShell from "@/components/store/StoreShell";
import { usePathname } from "next/navigation";

const TITLES: Record<string, string> = {
  "/store": "Home",
  "/store/recipes": "Recipes",
  "/store/stock": "Stock",
  "/store/account": "Account",
};

export default function StoreLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "/store";
  return <StoreShell title={TITLES[pathname] ?? "Store"}>{children}</StoreShell>;
}
