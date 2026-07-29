import type { Metadata, Viewport } from "next";
import { Outfit } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const outfit = Outfit({
  variable: "--font-outfit",
  subsets: ["latin"],
});

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
  // maximumScale/userScalable deliberately NOT set. They were `1` and `false`,
  // which disables pinch-zoom entirely — a WCAG 1.4.4 failure flagged by
  // Lighthouse on 2026-07-28. Anyone with low vision relying on screen
  // magnification could not zoom this app at all. The usual motive for locking
  // scale is stopping iOS from zooming on focused inputs, but that is caused by
  // sub-16px input font sizes, not by the user, and shouldn't be paid for by
  // removing zoom from everyone who needs it.
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
      <body className={`${outfit.variable} font-sans antialiased bg-[#0a0a0a] text-[#e5e5e5]`}>
        <Providers>{children}</Providers>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              if ('serviceWorker' in navigator) {
                window.addEventListener('load', () => {
                  navigator.serviceWorker.register('/sw.js').catch(() => {});
                });
              }
            `,
          }}
        />
      </body>
    </html>
  );
}

