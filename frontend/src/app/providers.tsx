"use client";

import { AuthProvider } from "@/context/AuthContext";
import ImpersonationBanner from "@/components/ImpersonationBanner";
import NativeApp from "@/components/NativeApp";

export function Providers({ children }: { children: React.ReactNode }) {
    return (
        <AuthProvider>
            <NativeApp>
                <ImpersonationBanner />
                {children}
            </NativeApp>
        </AuthProvider>
    );
}
