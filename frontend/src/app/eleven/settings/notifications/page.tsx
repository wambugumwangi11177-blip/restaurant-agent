"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import { useOwnerGet } from "@/hooks/useOwnerV11";

export default function SettingsNotificationsPage() {
  const { data } = useOwnerGet<{
    report_daily?: boolean;
    report_weekly?: boolean;
    report_monthly?: boolean;
    push?: boolean;
  }>("/api/v1/eleven/settings/notifications", []);

  return (
    <OwnerShell title="Notifications">
      <ul className="owner-glass-panel space-y-3 p-5 text-sm">
        <li className="flex justify-between">
          <span>Push alerts</span>
          <span className="text-zinc-400">{data?.push ? "On" : "Off"}</span>
        </li>
        <li className="flex justify-between">
          <span>Daily report (21:00 EAT)</span>
          <span className="text-zinc-400">{data?.report_daily ? "On" : "Off"}</span>
        </li>
        <li className="flex justify-between">
          <span>Weekly report (Monday)</span>
          <span className="text-zinc-400">{data?.report_weekly ? "On" : "Off"}</span>
        </li>
        <li className="flex justify-between">
          <span>Monthly P&L (1st)</span>
          <span className="text-zinc-400">{data?.report_monthly ? "On" : "Off"}</span>
        </li>
      </ul>
    </OwnerShell>
  );
}