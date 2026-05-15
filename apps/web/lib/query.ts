/**
 * TanStack Query client — Order 5.
 *
 * ``staleTime: Infinity`` is the M-2 architectural decision: WebSocket
 * messages are authoritative, so the cache should never auto-refetch.
 * The cockpit calls ``queryClient.setQueryData(...)`` from WS handlers
 * to push fresh data into the cache (Inngest/TkDodo pattern).
 *
 * ``gcTime: 5 minutes`` matches the M-1 replay buffer window — by the
 * time a query's data has been gc'd, the WS replay buffer would also
 * have rolled past; refetching is the right behaviour at that point.
 */
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: Infinity,
      gcTime: 5 * 60 * 1000,
      refetchOnWindowFocus: false,
    },
  },
});

// ``readonly unknown[]`` keeps each key tuple distinct without
// over-narrowing — the cockpit's TanStack Query keys are typed as
// arrays, not enum-like literal tuples.
export const cockpitKeys = {
  all: ["cockpit"] as readonly unknown[],
  health: () => ["cockpit", "health"] as readonly unknown[],
  projects: () => ["cockpit", "projects"] as readonly unknown[],
  project: (slug: string) => ["cockpit", "projects", slug] as readonly unknown[],
  kanban: (slug: string) =>
    ["cockpit", "projects", slug, "kanban"] as readonly unknown[],
  recentSessions: () =>
    ["cockpit", "sessions", "recent"] as readonly unknown[],
  session: (id: string) => ["cockpit", "session", id] as readonly unknown[],
  audit: (id: string) =>
    ["cockpit", "session", id, "audit"] as readonly unknown[],
  branches: (id: string) =>
    ["cockpit", "session", id, "branches"] as readonly unknown[],
  messages: (id: string, branchId: string | null) =>
    [
      "cockpit",
      "session",
      id,
      "messages",
      branchId ?? "active",
    ] as readonly unknown[],
  mind: (slug: string) =>
    ["cockpit", "projects", slug, "mind"] as readonly unknown[],
  mindStats: (slug: string) =>
    ["cockpit", "projects", slug, "mind", "stats"] as readonly unknown[],
  mindNotes: (slug: string, tier: string | null) =>
    [
      "cockpit",
      "projects",
      slug,
      "mind",
      "notes",
      tier ?? "all",
    ] as readonly unknown[],
};
