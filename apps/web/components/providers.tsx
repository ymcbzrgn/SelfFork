/**
 * Client-side providers wrapping every cockpit page.
 *
 * Mounts the TanStack Query provider so any cockpit component can
 * call ``useQuery`` / ``useMutation`` without re-creating the client.
 * Sidebar context lives next to it so the app shell renders without
 * additional wiring (Order 5 — kept tiny on purpose).
 */
"use client";

import * as React from "react";
import { QueryClientProvider } from "@tanstack/react-query";

import { queryClient } from "@/lib/query";
import { SidebarProvider } from "@/components/layout/sidebar-context";
import { TooltipProvider } from "@/components/ui/tooltip";

export function CockpitProviders({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <SidebarProvider>{children}</SidebarProvider>
      </TooltipProvider>
    </QueryClientProvider>
  );
}
