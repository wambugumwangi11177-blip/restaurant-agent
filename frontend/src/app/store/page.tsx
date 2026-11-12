"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CustodyDiagram } from "@/components/store/diagrams";
import { loadSetup, type SetupPayload } from "@/lib/storeSetup";

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
          You will photograph the invoice and the goods, then key the quantities. That screen comes next. The photos stay private.
        </p>
        <CustodyDiagram />
      </section>
      {error && <p className="text-sm text-red-300">{error}</p>}
      {!setup ? (
        <p className="text-sm text-zinc-400">Loading your steps…</p>
      ) : (
        <ol className="space-y-3">
          {setup.steps.map((step) => {
            const href = step.id === "account" ? "/store/account" : step.id === "recipes" ? "/store/recipes" : null;
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
                {step.id === "questionnaire" && step.questions && (
                  <ul className="mt-3 space-y-2 text-xs text-zinc-300">
                    {step.questions.map((question) => (
                      <li key={question.id} className="rounded-2xl border border-white/10 px-3 py-2">
                        {question.prompt}
                        <span className="mt-1 block text-zinc-500">
                          Yes opens {question.answers.find((answer) => answer.value === "yes")?.opens}
                        </span>
                      </li>
                    ))}
                  </ul>
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
