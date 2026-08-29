"use client";

// Reused directly from the Owner dashboard. The "View as" impersonate button
// is already gated to real Owner/Admin accounts client-side (see
// dashboard/staff/page.tsx's canImpersonate check) and require_role(ADMIN)
// server-side, so it correctly stays hidden for a Manager viewing this page.
import StaffRosterPage from "@/app/dashboard/staff/page";

export default function StaffManagerStaffPage() {
    return <StaffRosterPage />;
}
