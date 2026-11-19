"use client";

import { AuthProvider } from "@/context/AuthContext";
import ImpersonationBanner from "@/components/ImpersonationBanner";
import NativeApp from "@/components/NativeApp";
import ServiceWorkerRegister from "@/components/ServiceWorkerRegister";

export function Providers({ children }: { children: React.ReactNode }) {
    return (
        <AuthProvider>
            <ServiceWorkerRegister />
            <NativeApp>
                <ImpersonationBanner />
                {children}
            </NativeApp>
        </AuthProvider>
    );
}
