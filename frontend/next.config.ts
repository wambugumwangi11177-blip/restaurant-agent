import type { NextConfig } from "next";
import { LEGACY_AREA } from "./src/lib/owner/blocks";

// Security headers mirrored from vercel.json so they apply on EVERY host
// (next start, Docker, any non-Vercel deploy) — previously they existed only
// on Vercel, and a local/self-hosted deployment shipped with none.
const SECURITY_HEADERS = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "geolocation=(), microphone=(), camera=()" },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob:",
      "font-src 'self' data:",
      "connect-src 'self' https://*.up.railway.app http://localhost:8000 http://127.0.0.1:8000",
      "worker-src 'self'",
      "manifest-src 'self'",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
      "object-src 'none'",
    ].join("; "),
  },
];

// The two old owner shells (/vibanda for the Macsoft-fed restaurant, /demo for the demonstration one) are now one shell at /home,
// /os and /reports. Every old address still works: a deep link or a bookmark lands where its content lives now.
const LEGACY_SHELLS = ["vibanda", "demo"];
const legacyRedirects = LEGACY_SHELLS.flatMap((shell) => [
  { source: `/${shell}`, destination: "/home", permanent: false },
  { source: `/${shell}/os`, destination: "/os", permanent: false },
  { source: `/${shell}/reports`, destination: "/reports", permanent: false },
  ...Object.entries(LEGACY_AREA).map(([slug, area]) => ({ source: `/${shell}/${slug}`, destination: `/home#area-${area}`, permanent: false })),
  { source: `/${shell}/:other*`, destination: "/home", permanent: false },
]);

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // `next dev` writes AGENTS.md / CLAUDE.md into the project by default; this repository keeps its agent instructions at the root.
  agentRules: false,
  async redirects() {
    return legacyRedirects;
  },
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
