import type { Metadata } from "next";
import "./globals.css";

import { CommandPalette } from "@/components/command-palette";
import { KeyboardShortcutsOverlay } from "@/components/keyboard-shortcuts-overlay";
import { SidebarProvider } from "@/components/layout/sidebar-context";

export const metadata: Metadata = {
  title: "SelfFork Dashboard",
  description:
    "Live view over real SelfFork sessions. Reads only on-disk artifacts; no mock data.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-background text-foreground antialiased">
        <SidebarProvider>
          {children}
          <CommandPalette />
          <KeyboardShortcutsOverlay />
        </SidebarProvider>
      </body>
    </html>
  );
}
