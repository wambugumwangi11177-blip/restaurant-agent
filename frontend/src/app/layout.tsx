import type { Metadata, Viewport } from "next";
import { Outfit, DM_Sans, Space_Grotesk } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const outfit = Outfit({
  variable: "--font-outfit",
  subsets: ["latin"],
});

// Vibanda sketch fonts: DM Sans body, Space Grotesk display (font-display).
const dmSans = DM_Sans({
  variable: "--font-dm-sans",
  subsets: ["latin"],
});

const spaceGrotesk = Space_Grotesk({
  variable: "--font-space-grotesk",
  subsets: ["latin"],
});

// Opt every route out of static prerendering.
//
// Not a performance preference — a hard requirement of the nonce-based CSP in
// src/proxy.ts. A nonce must be unique per RESPONSE, and a statically
// prerendered page is rendered once at BUILD time, so its inline hydration
// scripts (`self.__next_f.push(...)`) can carry no nonce at all. Serving that
// build-time HTML under a per-request CSP means the browser blocks the
// hydration payload and the page never comes alive. Verified directly: with
// the routes left static, the served HTML contained 2 inline scripts and 0
// occurrences of the header's nonce.
//
// The cost here is small and was weighed: every route under this layout is an
// authenticated dashboard that fetches its own data client-side, so the
// prerendered output was an empty shell. If a genuinely static public page is
// ever added and this cost starts to matter, the fix is to scope the CSP and
// this flag to the routes that need them — not to put 'unsafe-inline' back.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Chakula — Restaurant Manager",
  description: "Simple restaurant management for Kenyan restaurants",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Chakula",
  },
};

export const viewport: Viewport = {
  themeColor: "#0a0a0a",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <head>
        <link rel="apple-touch-icon" href="/icon-192.png" />
      </head>
      <body className={`${outfit.variable} ${dmSans.variable} ${spaceGrotesk.variable} font-sans antialiased bg-[#0a0a0a] text-[#e5e5e5]`}>
        <Providers>{children}</Providers>
        {/* Loaded from /public rather than inlined: an inline script is what
            forced script-src 'unsafe-inline' into the CSP, which made the
            policy useless against the XSS it exists to stop. See
            src/proxy.ts and public/register-sw.js. */}
        <script src="/register-sw.js" defer />
      </body>
    </html>
  );
}

