"use client";
// Shared Loading / Empty / Error states — the SAME markup pattern on every
// Restaurant OS surface (design contract: answer first, owner's language).
export function OsLoading({ rows = 6 }: { rows?: number }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="rounded-2xl border border-[var(--border)] p-5 animate-pulse">
          <div className="h-3 w-24 rounded bg-[var(--muted-foreground)]/20" />
          <div className="h-8 w-32 rounded bg-[var(--muted-foreground)]/30 mt-3" />
          <div className="h-3 w-40 rounded bg-[var(--muted-foreground)]/20 mt-3" />
        </div>
      ))}
    </div>
  );
}

export function OsEmpty({ message, hint }: { message: string; hint?: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-[var(--border)] p-6 text-center">
      <p className="text-sm text-[var(--foreground)]">{message}</p>
      {hint ? <p className="text-xs text-[var(--muted-foreground)] mt-1">{hint}</p> : null}
    </div>
  );
}

export function OsError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-2xl border border-[var(--border)] p-6 text-center">
      <p className="text-sm">{message}</p>
      <button
        onClick={onRetry}
        className="mt-3 rounded-full px-4 py-2 text-sm bg-[var(--accent)] text-white"
      >
        Retry
      </button>
    </div>
  );
}