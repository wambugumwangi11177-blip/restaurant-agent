import { NextRequest, NextResponse } from "next/server";

/**
 * Content-Security-Policy, generated per request so it can carry a nonce.
 *
 * WHY THIS FILE EXISTS
 * The CSP used to live as a static string in next.config.ts and vercel.json,
 * and it contained `script-src 'self' 'unsafe-inline'`. 'unsafe-inline' allows
 * ANY injected inline <script> to execute, which is precisely the attack a CSP
 * is supposed to stop — the policy looked like a control and was not one. It
 * was there because two things need inline scripts: the service-worker
 * registration snippet in app/layout.tsx, and Next.js's own RSC hydration
 * payload (`self.__next_f.push(...)`).
 *
 * The registration snippet moved to public/register-sw.js, so plain
 * `script-src 'self'` covers it. Next.js's hydration scripts cannot move, so
 * they get a per-request nonce instead: Next reads the Content-Security-Policy
 * header off the *request* (set below via NextResponse.next), extracts the
 * nonce, and stamps it onto every script tag it emits.
 *
 * A nonce has to be unique per response, so it cannot come from a static
 * config — which is why the CSP is issued here and NOWHERE else. Do not add a
 * Content-Security-Policy back to next.config.ts or vercel.json: a browser
 * given two CSP headers enforces the intersection, and a static policy without
 * this nonce would block the very hydration scripts this one permits, taking
 * the whole app down. The other security headers (HSTS, X-Frame-Options,
 * nosniff, Referrer-Policy, Permissions-Policy) stay in those static configs
 * on purpose: they need no per-request value, and living there means they also
 * cover the static-asset paths this middleware deliberately skips.
 *
 * TRADEOFF: pages that receive a nonce are rendered dynamically rather than
 * served from the static prerender. For this app that costs little — every
 * dashboard route is authenticated and fetches its data client-side, so the
 * prerendered output was a shell either way.
 */

const isDev = process.env.NODE_ENV !== "production";

/**
 * The exact origin the browser is allowed to call the API on.
 *
 * Derived from NEXT_PUBLIC_API_URL — the same value api.ts uses to build every
 * request — rather than hardcoded, so the policy cannot drift from where the
 * app actually talks. The previous CSP hardcoded `https://*.up.railway.app`,
 * which had two problems: that wildcard permits connections to ANY app on
 * Railway's shared domain, including someone else's, and it would silently
 * block every API call the moment the backend moves off Railway. That move is
 * not hypothetical — HARDENING_STATUS.md has a pending Railway-account
 * migration, and a CSP failure presents as "the app loads but nothing works",
 * which is a miserable thing to debug.
 *
 * Falls back to the old wildcard only when NEXT_PUBLIC_API_URL is unset at
 * build time. A missing env var should degrade to the previous behavior, not
 * to a dead app.
 */
const API_ORIGINS: string[] = (() => {
  const raw = process.env.NEXT_PUBLIC_API_URL;
  if (raw) {
    try {
      return [new URL(raw).origin];
    } catch {
      // Malformed URL — fall through to the wildcard rather than emitting a
      // broken directive.
    }
  }
  return ["https://*.up.railway.app"];
})();

export function proxy(request: NextRequest) {
  // 128 bits of CSPRNG, base64'd. Uniqueness per response is the entire
  // security property of a nonce — never cache, reuse, or derive this.
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");

  const connectSrc = [
    "'self'",
    ...API_ORIGINS,
    // Dev-only. Shipping these in production would let the page talk to a
    // service running on the viewer's own machine.
    ...(isDev ? ["http://localhost:8000", "http://127.0.0.1:8000"] : []),
  ].join(" ");

  const csp = [
    "default-src 'self'",
    // No 'unsafe-inline'. Next's inline hydration scripts run via the nonce;
    // everything else must be a file served from this origin.
    `script-src 'self' 'nonce-${nonce}'`,
    // style-src KEEPS 'unsafe-inline', and that is a deliberate, narrower
    // call rather than an oversight: React writes style="" attributes
    // directly (framer-motion does it on every animation frame), and a nonce
    // cannot apply to a style attribute — only to a <style> element. Removing
    // it would break the UI comprehensively. Inline CSS cannot execute script,
    // so the residual risk is defacement/exfil-via-selector, not RCE.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    // next/font self-hosts Google Fonts at build time, so no external origin.
    "font-src 'self' data:",
    `connect-src ${connectSrc}`,
    "worker-src 'self'",
    "manifest-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
  ].join("; ");

  // Set on the REQUEST so the Next renderer can read the nonce back out...
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  // ...and on the RESPONSE so the browser actually enforces it.
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: [
    {
      // Documents only. Static assets and images are served straight from the
      // CDN and carry no scripts of their own; the static header block in
      // next.config.ts/vercel.json still covers them for nosniff + HSTS.
      source: "/((?!api|_next/static|_next/image|favicon.ico|icon-|manifest.json|sw.js|register-sw.js).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
