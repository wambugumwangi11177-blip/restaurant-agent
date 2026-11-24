"use client";

import { useEffect, useState } from "react";
import OwnerShell from "@/components/eleven/OwnerShell";
import { GlassCard, SectionLabel } from "@/components/eleven/EmptyPanels";
import api from "@/lib/api";

const LOGIN_ROLES = ["manager", "stockkeeper", "controller"];
const ROSTER_ROLES = ["waiter", "kitchen", "supervisor", "host", "runner"];

type SetupAnswer = {
  question_id: string;
  label: string;
  value: string;
  delegated?: boolean;
};

type Person = {
  user_id: number;
  email: string;
  name?: string;
  staff_role: string | null;
  account: string;
  answers?: SetupAnswer[];
  questionnaire?: string;
  routing_mode?: string;
};

export default function ElevenStaffPage() {
  const [people, setPeople] = useState<Person[]>([]);
  const [routingMode, setRoutingMode] = useState<string | null>(null);
  const [roster, setRoster] = useState<{ id: number; name: string; role_title: string }[]>([]);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [staffRole, setStaffRole] = useState("stockkeeper");
  const [rosterName, setRosterName] = useState("");
  const [rosterRole, setRosterRole] = useState("waiter");
  const [dailyPay, setDailyPay] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function load() {
    const [activity, rosterRes] = await Promise.all([
      api.get("/api/v1/staff-setup/activity"),
      api.get("/api/v1/team/roster"),
    ]);
    setPeople(activity.data.people ?? []);
    setRoutingMode(activity.data.routing_mode ?? null);
    setRoster(rosterRes.data ?? []);
  }

  useEffect(() => {
    load().catch(() => setError("Staff could not be loaded."));
  }, []);

  async function createLogin(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      const manager = staffRole === "stockkeeper" || staffRole === "controller";
      await api.post("/api/v1/staff/", {
        name,
        role_title: staffRole,
        create_login: true,
        email,
        ...(password ? { password } : {}),
        staff_role: staffRole,
      });
      setMessage(
        manager
          ? "Login created. They choose their own password on first sign-in, then set a 4-digit PIN."
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

  async function createRoster(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await api.post("/api/v1/team/roster", {
        name: rosterName,
        role_title: rosterRole,
        daily_pay_rate_cents: dailyPay ? Math.round(Number(dailyPay) * 100) : null,
      });
      setMessage("Roster member added — no login.");
      setRosterName("");
      setDailyPay("");
      await load();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Roster member was not added.");
    }
  }

  return (
    <OwnerShell title="Staff">
      <SectionLabel>Dashboard login</SectionLabel>
      <p className="mb-3 text-sm text-zinc-400">Manager, store (Jack), and accountant only. Waiters, kitchen, and supervisors are roster-only below.</p>
      <GlassCard>
        <form onSubmit={createLogin} className="space-y-3">
          <label className="block text-sm">
            Name
            <input required value={name} onChange={(event) => setName(event.target.value)} className="leviii-input mt-1 min-h-11 w-full rounded-2xl px-3" />
          </label>
          <label className="block text-sm">
            Email
            <input required inputMode="email" autoComplete="off" value={email} onChange={(event) => setEmail(event.target.value)} className="leviii-input mt-1 min-h-11 w-full rounded-2xl px-3" />
          </label>
          {staffRole === "manager" && (
            <label className="block text-sm">
              Temporary password
              <input required type="password" value={password} onChange={(event) => setPassword(event.target.value)} className="leviii-input mt-1 min-h-11 w-full rounded-2xl px-3" />
            </label>
          )}
          {(staffRole === "stockkeeper" || staffRole === "controller") && (
            <p className="text-sm text-zinc-400">No preset password. They set one at first sign-in.</p>
          )}
          <label className="block text-sm">
            Role
            <select value={staffRole} onChange={(event) => setStaffRole(event.target.value)} className="leviii-input mt-1 min-h-11 w-full rounded-2xl px-3">
              {LOGIN_ROLES.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" className="leviii-btn-primary min-h-11 w-full">
            Create login
          </button>
        </form>
      </GlassCard>

      <SectionLabel>Floor team (no login)</SectionLabel>
      <GlassCard>
        <form onSubmit={createRoster} className="space-y-3">
          <label className="block text-sm">
            Name
            <input required value={rosterName} onChange={(e) => setRosterName(e.target.value)} className="leviii-input mt-1 min-h-11 w-full rounded-2xl px-3" />
          </label>
          <label className="block text-sm">
            Role label
            <select value={rosterRole} onChange={(e) => setRosterRole(e.target.value)} className="leviii-input mt-1 min-h-11 w-full rounded-2xl px-3">
              {ROSTER_ROLES.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            Daily pay rate (KES, optional — owner / accountant only)
            <input inputMode="decimal" value={dailyPay} onChange={(e) => setDailyPay(e.target.value)} className="leviii-input mt-1 min-h-11 w-full rounded-2xl px-3" />
          </label>
          <button type="submit" className="leviii-btn-primary min-h-11 w-full">
            Add to roster
          </button>
        </form>
      </GlassCard>

      {error && <p className="text-sm text-red-300">{error}</p>}
      {message && <p className="text-sm text-[var(--text)]">{message}</p>}

      <SectionLabel>Roster</SectionLabel>
      {roster.length === 0 ? (
        <GlassCard>
          <p className="text-sm text-zinc-300">No floor team yet.</p>
        </GlassCard>
      ) : (
        <ul className="space-y-2">
          {roster.map((person) => (
            <li key={person.id} className="owner-glass-panel rounded-2xl p-4 text-sm">
              <p className="text-[var(--text)]">{person.name}</p>
              <p className="text-zinc-400">{person.role_title}</p>
            </li>
          ))}
        </ul>
      )}

      <SectionLabel>Store setup answers</SectionLabel>
      {routingMode && (
        <p className="mb-2 text-sm text-zinc-400">
          Restock routing: <span className="text-zinc-200">{routingMode.replace(/_/g, " ")}</span>
        </p>
      )}
      {people.length === 0 ? (
        <GlassCard>
          <p className="text-sm text-zinc-300">No storekeeper setup record yet.</p>
        </GlassCard>
      ) : (
        <ul className="space-y-3">
          {people.map((person) => (
            <li key={person.user_id} className="owner-glass-panel rounded-3xl p-4 text-sm">
              <p className="font-medium">{person.name || person.email}</p>
              <p className="text-zinc-400 capitalize">{person.staff_role} · questionnaire {person.questionnaire ?? "pending"}</p>
              {(person.answers ?? []).length > 0 && (
                <ul className="mt-3 space-y-1 border-t border-white/10 pt-3 text-zinc-300">
                  {person.answers!.map((answer) => (
                    <li key={answer.question_id}>
                      <span className="text-zinc-500">{answer.question_id.replace(/_/g, " ")}:</span>{" "}
                      {answer.label || answer.value}
                      {answer.delegated ? " (sent to owner)" : ""}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
    </OwnerShell>
  );
}