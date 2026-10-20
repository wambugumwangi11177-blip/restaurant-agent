"use client";
import StateChip from "@/components/owner/StateChip";
import type { OwnerHome } from "@/lib/owner/types";

/** Zone 5 — LEVIII's read: a short note in plain words, only when every number in it is backed; otherwise it is not shown at all. */
export default function ReadNote({ read }: { read: OwnerHome["read"] }) {
  if (!read.text) return null;
  return (
    <div className="rounded-xl border border-[var(--v-border)] bg-[var(--v-card)] p-5">
      <div className="mb-2 flex items-center gap-2"><StateChip block={read} /></div>
      <p className="whitespace-pre-line text-sm leading-relaxed">{read.text}</p>
    </div>
  );
}
