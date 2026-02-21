import type { Metadata } from "next";
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
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={`${outfit.variable} font-sans antialiased bg-[#0a0a0a] text-[#e5e5e5]`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
