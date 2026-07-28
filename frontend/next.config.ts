import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Sentry is wired up (main.py, traces_sample_rate=0.2) and receives frontend
  // errors, but without source maps every frontend stack trace arrives as
  // minified single-letter-variable noise — the integration is paid for and
  // effectively unreadable. Verified 2026-07-28: the production build emitted
  // 0 .map files, so this was silently degrading the error tracking already
  // in place. Next serves these with `x-robots-tag: noindex`.
  productionBrowserSourceMaps: true,
};

export default nextConfig;
