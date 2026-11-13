"use client";

import OwnerShell from "@/components/eleven/OwnerShell";
import { GlassCard, SectionLabel, SolidNumberCard, WaitingNotice } from "@/components/eleven/EmptyPanels";
import { useOwnerFeed } from "@/components/eleven/OwnerFeed";

export default function ElevenMoneyPage() {
  const { data, error } = useOwnerFeed();
  const money = data?.cards?.find((card) => card.id === "money");
  return (
    <OwnerShell title="My Money">
      {!data && !error && <p className="text-sm text-zinc-400">Loading…</p>}
      {data && (
        <>
          <SolidNumberCard
            title="What you kept this month"
            body={data.till_live ? "Till is live" : "Waiting for the till"}
            hint={money?.sentence}
          />
          <SectionLabel>Approved bills</SectionLabel>
          <GlassCard>
            {(data.approved_bills ?? []).length === 0 ? (
              <WaitingNotice>No bill has been approved yet. Managers send rent, gas, electricity, water, and salaries. You approve them here before they count.</WaitingNotice>
            ) : (
              <ul className="space-y-2 text-sm">
                {data.approved_bills?.map((bill) => <li key={bill}>{bill}</li>)}
              </ul>
            )}
          </GlassCard>
          {(data.unknown_costs ?? []).length > 0 && (
            <>
              <SectionLabel>Still unknown</SectionLabel>
              <GlassCard>
                <p className="text-sm">
                  {(data.unknown_costs?.length ?? 0) === 1
                    ? `${data.unknown_costs?.[0]} has no amount yet.`
                    : `${data.unknown_costs?.join(", ")} have no amount yet.`}
                </p>
              </GlassCard>
            </>
          )}
        </>
      )}
    </OwnerShell>
  );
}
