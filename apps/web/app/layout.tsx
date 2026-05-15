import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

import { CockpitProviders } from "@/components/providers";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
  weight: ["400", "500", "600", "700", "800"],
});

export const metadata: Metadata = {
  title: "SelfFork",
  description:
    "An autonomous coding partner you actually trust.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-screen bg-background text-on-surface antialiased font-body">
        <CockpitProviders>{children}</CockpitProviders>
      </body>
    </html>
  );
}
