import type { Metadata } from "next";
import { Shell } from "@/components/shell";
import "./globals.css";

export const metadata: Metadata = { title: "Company OS", description: "The company's internal operating system" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
