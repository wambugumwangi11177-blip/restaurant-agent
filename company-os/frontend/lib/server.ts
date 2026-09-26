// Server-only helpers for the backend-for-frontend (BFF) routes.
// The API token lives in an httpOnly cookie: browser JavaScript never sees it.
import type { NextRequest } from "next/server";

export const BACKEND_URL = (process.env.BACKEND_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const SESSION_COOKIE = "cos_session";

/** Mutating requests must come from this site (CSRF defence in addition to SameSite=Lax). */
export function sameOrigin(req: NextRequest): boolean {
  const origin = req.headers.get("origin");
  if (!origin) return true; // same-origin navigations and non-browser clients omit Origin
  const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}
