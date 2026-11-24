"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import TeamScheduleEditor from "@/components/team/TeamScheduleEditor";

export default function ElevenSchedulePage() {
  return (
    <OwnerShell title="Schedule">
      <TeamScheduleEditor />
    </OwnerShell>
  );
}