"use client";

// Reused directly from the Owner dashboard — this page has no internal
// /dashboard/* links and fetches its own data via GET /ai/roi, which is
// already gated server-side to Manager/Controller/Owner (directive 015).
import RoiPage from "@/app/dashboard/roi/page";

export default function StaffControllerRoiPage() {
    return <RoiPage />;
}
