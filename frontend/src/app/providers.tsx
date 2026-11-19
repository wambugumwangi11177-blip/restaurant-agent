"use client";

import { AuthProvider } from "@/context/AuthContext";
import ImpersonationBanner from "@/components/ImpersonationBanner";
import NativeApp from "@/components/NativeApp";
import ServiceWorkerRegister from "@/components/ServiceWorkerRegister";
import AppLockGate from "@/components/auth/AppLockGate";

export function Providers({ children }: { children: React.ReactNode }) {
    return (
        <AuthProvider>
            <AppLockGate>
                <ServiceWorkerRegister />
                <NativeApp>
                    <ImpersonationBanner />
                    {children}
                </NativeApp>
            </AppLockGate>
        </AuthProvider>
    );
}
