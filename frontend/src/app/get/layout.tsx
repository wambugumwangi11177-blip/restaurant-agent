import type { Metadata, Viewport } from "next";

export const metadata: Metadata = {
  title: "Get LEVIII Store",
  description: "Install LEVIII Store on a phone, tablet, or computer.",
  manifest: "/store-manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "LEVIII Store",
  },
  icons: {
    icon: [
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/icon-192.png", sizes: "192x192" }],
  },
};

export const viewport: Viewport = {
  themeColor: "#070708",
  width: "device-width",
  initialScale: 1,
};

export default function GetLayout({ children }: { children: React.ReactNode }) {
  return children;
}
