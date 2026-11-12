"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CustodyDiagram } from "@/components/store/diagrams";
import { hasModule, loadSetup, type SetupPayload } from "@/lib/storeSetup";

export default function StoreHomePage() {
  const [setup, setSetup] = useState<SetupPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    loadSetup().then(setSetup).catch(() => setError("The setup steps could not be loaded."));
  }, []);

  return (
    <div className="space-y-4">
      <section className="owner-glass-panel rounded-3xl p-4">
        <h2 className="text-sm font-semibold">How a delivery is kept</h2>
        <p className="mt-1 text-xs leading-5 text-zinc-400">
          Photograph the invoice and the goods, then key the quantities. Prices stay with the owner.
        </p>
        <CustodyDiagram />
      </section>
      {setup?.stock_followup?.status === "waiting_on_pos" && (
        <section className="owner-glass-panel rounded-3xl p-4">
          <h2 className="font-semibold">Stock</h2>
          <p className="mt-2 text-sm leading-6 text-zinc-300">{setup.stock_followup.label}</p>
        </section>
      )}
      {setup?.stock_followup?.pending && (
        <section className="owner-glass-panel rounded-3xl p-4">
          <p className="text-xs uppercase tracking-[0.14em] text-zinc-500">Pending</p>
          <h2 className="mt-1 font-semibold">Enter store stock</h2>
          <p className="mt-2 text-sm leading-6 text-zinc-300">{setup.stock_followup.pending}</p>
        </section>
      )}
      {error && <p className="text-sm text-red-300">{error}</p>}
      {setup?.app_unlocked && (
        <section className="owner-glass-panel rounded-3xl p-4">
          <h2 className="font-semibold">Today</h2>
          <ul className="mt-3 space-y-2 text-sm">
            <li><Link href="/store/chefs" className="underline">Chefs</Link></li>
            {hasModule(setup, "deliveries") && <li><Link href="/store/deliveries" className="underline">Deliveries</Link></li>}
            {hasModule(setup, "store-issue") && <li><Link href="/store/issue" className="underline">Hand to the kitchen</Link></li>}
            {hasModule(setup, "waste") && <li><Link href="/store/waste" className="underline">Thrown away</Link></li>}
            {hasModule(setup, "day-close") && <li><Link href="/store/close" className="underline">Close the day</Link></li>}
          </ul>
        </section>
      )}
      {!setup ? (
        <p className="text-sm text-zinc-400">Loading your steps…</p>
      ) : (
        <ol className="space-y-3">
          {setup.steps.map((step) => {
            const href = step.id === "account" ? "/store/account" : step.id === "recipes" ? "/store/recipes" : step.id === "questionnaire" ? "/store/questions" : null;
            const open = step.state !== "locked" && href;
            const body = (
              <>
                <div className="flex items-center justify-between gap-3">
                  <h2 className="font-semibold">{step.title}</h2>
                  <span className="rounded-full border border-white/20 px-2 py-0.5 text-[10px] uppercase tracking-wide text-zinc-300">
                    {step.state}
                  </span>
                </div>
                <p className="mt-2 text-sm text-zinc-300">Unlocks: {step.unlocks}</p>
                {step.locked_reason && <p className="mt-2 text-xs leading-5 text-zinc-400">{step.locked_reason}</p>}
                {step.id === "questionnaire" && step.state === "locked" && step.questions && (
                  <p className="mt-2 text-xs text-zinc-500">{step.questions.length} short questions. They open after the recipes.</p>
                )}
              </>
            );
            if (open && href) {
              return (
                <li key={step.id}>
                  <Link href={href} className="owner-glass-panel block rounded-3xl p-4">
                    {body}
                  </Link>
                </li>
              );
            }
            return (
              <li key={step.id} className="owner-glass-panel rounded-3xl p-4 opacity-90">
                {body}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
