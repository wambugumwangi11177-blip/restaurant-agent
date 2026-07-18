"use client";

// Reused directly from the Owner dashboard — no internal /dashboard/* links,
// backend-gated to Manager/Owner already (_MARKETING_WRITE in routers/ai.py).
import MarketingPage from "@/app/dashboard/marketing/page";

export default function StaffManagerMarketingPage() {
    return <MarketingPage />;
}
