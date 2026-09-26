"use client";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-zinc-500 dark:text-zinc-400">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cx("rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900", className)}>
      {children}
    </div>
  );
}

export function Button({ variant = "primary", className, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }) {
  const styles = {
    primary: "bg-zinc-900 text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300",
    secondary: "border border-zinc-300 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800",
    danger: "bg-red-600 text-white hover:bg-red-500",
  }[variant];
  return (
    <button
      {...p}
      className={cx("rounded-md px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50", styles, className)}
    />
  );
}

const field = "w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-950";

export function Input(p: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...p} className={cx(field, p.className)} />;
}

export function Textarea(p: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...p} className={cx(field, "font-[inherit]", p.className)} />;
}

export function Select(p: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...p} className={cx(field, p.className)} />;
}

export function Label({ children, text }: { children: ReactNode; text: string }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-xs font-medium text-zinc-500 dark:text-zinc-400">{text}</span>
      {children}
    </label>
  );
}

const tones: Record<string, string> = {
  green: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  amber: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  red: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  zinc: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  blue: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300",
};

export function Badge({ children, tone = "zinc" }: { children: ReactNode; tone?: keyof typeof tones | string }) {
  return <span className={cx("inline-block rounded px-1.5 py-0.5 text-xs font-medium", tones[tone] ?? tones.zinc)}>{children}</span>;
}

export function statusTone(status: string): string {
  if (["succeeded", "executed", "done", "approved", "accepted", "ok"].includes(status)) return "green";
  if (["pending", "pending_approval", "open", "in_progress", "proposed", "running"].includes(status)) return "amber";
  if (["failed", "rejected", "denied", "error", "refused", "spend_capped", "llm_unavailable", "cancelled"].includes(status)) return "red";
  return "zinc";
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-300">{error}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-sm text-zinc-500 dark:text-zinc-400">{children}</p>;
}

export function Pre({ children }: { children: ReactNode }) {
  return <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded bg-zinc-100 p-2 text-xs dark:bg-zinc-950">{children}</pre>;
}
