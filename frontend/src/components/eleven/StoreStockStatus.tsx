"use client";

import { useEffect, useState } from "react";
import { GlassCard, SectionLabel } from "@/components/eleven/EmptyPanels";
import api from "@/lib/api";

type Followup = { status: string; label: string; pending: string | null };
type Person = { user_id: number; email: string; stock_followup?: Followup | null };

export function StoreStockStatus() {
  const [people, setPeople] = useState<Person[]>([]);

  useEffect(() => {
    api.get("/api/v1/staff-setup/activity")
      .then((response) => {
        const rows = ((response.data?.people ?? []) as Person[]).filter((person) => person.stock_followup);
        setPeople(rows);
      })
      .catch(() => setPeople([]));
  }, []);

  if (people.length === 0) return null;

  return (
    <>
      <SectionLabel>Store stock</SectionLabel>
      {people.map((person) => (
        <GlassCard key={person.user_id}>
          <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">{person.email}</p>
          <p className="mt-2 text-sm leading-6">{person.stock_followup?.label}</p>
          {person.stock_followup?.status === "waiting_on_pos" && (
            <p className="mt-2 text-xs text-zinc-400">Waiting on the POS webhook</p>
          )}
          {person.stock_followup?.status === "count_when_live" && (
            <p className="mt-2 text-xs text-zinc-400">Pending for the storekeeper</p>
          )}
        </GlassCard>
      ))}
    </>
  );
}
