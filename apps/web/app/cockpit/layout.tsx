/**
 * Cockpit shell layout — Order 5.
 *
 * 4 tabs: Mission / Run / Chat / Context. The active tab lives in the
 * URL (``?tab=...``) so deep links survive page reloads and the
 * static export stays compatible (no dynamic ``[tab]`` segments).
 *
 * The actual tab content is rendered by ``app/cockpit/page.tsx``;
 * Orders 6-9 swap their respective tab body in.
 */
"use client";

import { Suspense } from "react";

import { AppShell } from "@/components/layout/app-shell";

export default function CockpitLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AppShell title="Cockpit">
      <Suspense fallback={<CockpitFallback />}>{children}</Suspense>
    </AppShell>
  );
}

function CockpitFallback() {
  return (
    <div className="h-64 animate-pulse rounded-md bg-muted/40" />
  );
}
