"use client";

import { useEffect, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import { GlassCard, SectionLabel } from "@/components/eleven/EmptyPanels";
import api from "@/lib/api";

type Person = {
  user_id: number;
  email: string;
  name?: string;
  staff_role: string | null;
  account: string;
  recipes: string;
  questionnaire: string;
  app_unlocked: boolean;
  answers?: { question_id: string; label: string; delegated: boolean; delegate_to: string | null; unlocks: string | null }[];
  stock_followup?: { status: string; label: string; pending: string | null } | null;
};

type Entry = { id: number; at: string | null; email: string | null; action: string; summary: string };

const ROLES = ["stockkeeper", "kitchen", "manager", "supervisor", "controller", "waiter"];

export default function ElevenStaffPage() {
  const [people, setPeople] = useState<Person[]>([]);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [missingRecipes, setMissingRecipes] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [staffRole, setStaffRole] = useState("stockkeeper");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function load() {
    const response = await api.get("/api/v1/staff-setup/activity");
    setPeople(response.data.people ?? []);
    setEntries(response.data.entries ?? []);
    setMissingRecipes(response.data.recipe_gap?.missing_count ?? 0);
  }

  useEffect(() => {
    load().catch(() => setError("Setup progress could not be loaded."));
  }, []);

  async function createLogin(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      await api.post("/api/v1/staff/", {
        name,
        role_title: staffRole,
        create_login: true,
        email,
        password,
        staff_role: staffRole,
      });
      setMessage(
        staffRole === "stockkeeper" || staffRole === "controller"
          ? "Login created. They must change this password and set a 4-digit PIN on first sign-in."
          : "Login created.",
      );
      setName("");
      setEmail("");
      setPassword("");
      await load();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "The login was not created.");
    }
  }

  return (
    <OwnerShell title="Staff">
      <SectionLabel>Create a login</SectionLabel>
      <GlassCard>
        <form onSubmit={createLogin} className="space-y-3">
          <label className="block text-sm">
            Name
            <input required value={name} onChange={(event) => setName(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
          </label>
          <label className="block text-sm">
            Email
            <input required inputMode="email" autoComplete="off" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="jack@eleven.leviii" className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
          </label>
          <label className="block text-sm">
            Temporary password
            <input required type="password" value={password} onChange={(event) => setPassword(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/30 px-3" />
          </label>
          <label className="block text-sm">
            Role
            <select value={staffRole} onChange={(event) => setStaffRole(event.target.value)} className="mt-1 min-h-11 w-full rounded-2xl border border-white/15 bg-black/40 px-3">
              {ROLES.map((role) => <option key={role}>{role}</option>)}
            </select>
          </label>
          {error && <p className="text-sm text-red-300">{error}</p>}
          {message && <p className="text-sm text-zinc-200">{message}</p>}
          <button type="submit" className="min-h-11 w-full rounded-full bg-white font-semibold text-black">
            Create login
          </button>
        </form>
      </GlassCard>
      <SectionLabel>Recipes</SectionLabel>
      <GlassCard>
        <p className="text-sm text-zinc-300">
          {missingRecipes == null ? "Loading…" : missingRecipes === 0 ? "No dish is waiting for a recipe." : missingRecipes === 1 ? "1 dish still has no recipe." : `${missingRecipes} dishes still have no recipe.`}
        </p>
      </GlassCard>
      <SectionLabel>Setup progress</SectionLabel>
      {people.length === 0 ? (
        <GlassCard>
          <p className="text-sm text-zinc-300">No storekeeper has a setup record yet.</p>
        </GlassCard>
      ) : (
        <ul className="space-y-3">
          {people.map((person) => (
            <li key={person.user_id} className="owner-glass-panel rounded-3xl p-4 text-sm">
              <p className="font-semibold">{person.name || person.email}</p>
              <p className="text-[11px] text-zinc-500">{person.email}</p>
              <p className="mt-1 text-zinc-400">{person.staff_role}</p>
              <p className="mt-2">Account {person.account} · Recipes {person.recipes} · Questions {person.questionnaire}</p>
              {person.stock_followup && <p className="mt-2 text-zinc-300">{person.stock_followup.label}</p>}
              {(person.answers ?? []).length > 0 && (
                <ul className="mt-2 space-y-1 text-zinc-300">
                  {person.answers?.map((answer) => (
                    <li key={answer.question_id}>
                      {answer.label}{answer.delegated ? ` — sent to the ${answer.delegate_to === "accountant" ? "accountant" : "owner"}` : ""}
                      {answer.unlocks ? ` · opens ${answer.unlocks}` : ""}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
      <SectionLabel>What was entered</SectionLabel>
      {entries.length === 0 ? (
        <GlassCard>
          <p className="text-sm text-zinc-300">Nothing has been entered yet.</p>
        </GlassCard>
      ) : (
        <ul className="space-y-2">
          {entries.map((entry) => (
            <li key={entry.id} className="owner-glass-panel rounded-3xl p-4 text-sm">
              <p>{entry.summary}</p>
              <p className="mt-1 text-xs text-zinc-500">{entry.email} · {entry.at}</p>
            </li>
          ))}
        </ul>
      )}
    </OwnerShell>
  );
}
