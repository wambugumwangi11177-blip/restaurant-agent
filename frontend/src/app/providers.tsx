"use client";

import { AuthProvider } from "@/context/AuthContext";
import ImpersonationBanner from "@/components/ImpersonationBanner";

export function Providers({ children }: { children: React.ReactNode }) {
    return (
        <AuthProvider>
            <ImpersonationBanner />
            {children}
        </AuthProvider>
    );
}
