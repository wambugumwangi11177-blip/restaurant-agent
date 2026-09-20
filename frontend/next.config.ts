import type { NextConfig } from "next";

// Security headers mirrored from vercel.json so they apply on EVERY host
// (next start, Docker, any non-Vercel deploy) — previously they existed only
// on Vercel, and a local/self-hosted deployment shipped with none.
//
// Content-Security-Policy is deliberately ABSENT from this list. It is issued
// per request by src/proxy.ts, because it carries a nonce that has to be
// unique per response and therefore cannot be a static string. Adding a CSP
// back here would give the browser two policies to intersect, and this one —
// lacking that nonce — would block Next.js's own hydration scripts and break
// the app. Every header below is safe as a constant, and living here means
// they also cover the static-asset paths the middleware skips.
const SECURITY_HEADERS = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "geolocation=(), microphone=(), camera=()" },
  // HSTS was set on the backend (backend/middleware/security_headers.py) but
  // on nothing the browser loads the HTML from. Vercel adds it automatically
  // on *.vercel.app, which meant production was probably covered by the
  // platform and every other host — next start, Docker, a self-hosted deploy —
  // shipped with none. That is the exact gap this whole block exists to close,
  // so it is stated here rather than left to the platform.
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains",
  },
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: SECURITY_HEADERS,
      },
      {
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: "no-cache" },
          { key: "Service-Worker-Allowed", value: "/" },
        ],
      },
      {
        source: "/manifest.json",
        headers: [{ key: "Cache-Control", value: "no-cache" }],
      },
    ];
  },
};

export default nextConfig;
