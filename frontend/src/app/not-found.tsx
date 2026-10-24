import Link from "next/link";

export default function NotFound() {
  return (
    <main className="vibanda-theme flex min-h-screen items-center justify-center px-6">
      <div className="max-w-md text-center">
        <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--v-muted-foreground)]">LEVIII</p>
        <h1 className="font-display mt-2 text-3xl font-semibold tracking-tight">That page is not here</h1>
        <p className="mt-3 text-sm text-[var(--v-muted-foreground)]">
          The address does not match a screen in this restaurant. Home is the place to start.
        </p>
        <Link href="/" className="mt-6 inline-flex min-h-11 items-center rounded-lg bg-[var(--v-primary)] px-4 text-sm font-bold text-[var(--v-primary-foreground)]">
          Go to your home
        </Link>
      </div>
    </main>
  );
}
