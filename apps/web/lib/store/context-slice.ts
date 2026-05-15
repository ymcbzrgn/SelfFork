/**
 * Context tab slice — Order 5 placeholder + Order 9's recall/graph fields.
 */
import type { StateCreator } from "zustand";

import type { CockpitStore } from "./index";

export type MindTier =
  | "working"
  | "episodic"
  | "semantic_graph"
  | "procedural"
  | "reflection"
  | "recall";

export interface ContextSlice {
  contextActiveProjectSlug: string | null;
  contextExpandedTiers: ReadonlySet<MindTier>;
  contextRecallQuery: string;
  contextRecallTier: MindTier | null;
  contextGraphSeed: string;
  setContextActiveProject: (slug: string | null) => void;
  toggleContextTier: (tier: MindTier) => void;
  setContextRecallQuery: (q: string) => void;
  setContextRecallTier: (tier: MindTier | null) => void;
  setContextGraphSeed: (seed: string) => void;
}

const DEFAULT_EXPANDED: ReadonlySet<MindTier> = new Set([
  "working",
  "episodic",
] as const);

export const createContextSlice: StateCreator<
  CockpitStore,
  [["zustand/devtools", never]],
  [],
  ContextSlice
> = (set) => ({
  contextActiveProjectSlug: null,
  contextExpandedTiers: DEFAULT_EXPANDED,
  contextRecallQuery: "",
  contextRecallTier: null,
  contextGraphSeed: "",
  setContextActiveProject: (slug) =>
    // Order 9 audit fix: project switch resets per-project view state
    // (expanded-tier set, recall query) so cross-project bleed (e.g.
    // T3 expanded in A still expanded in B with no graph data) doesn't
    // surprise the operator.
    set({
      contextActiveProjectSlug: slug,
      contextExpandedTiers: DEFAULT_EXPANDED,
      contextRecallQuery: "",
      contextRecallTier: null,
      contextGraphSeed: "",
    }),
  toggleContextTier: (tier) =>
    set((state) => {
      const next = new Set(state.contextExpandedTiers);
      if (next.has(tier)) {
        next.delete(tier);
      } else {
        next.add(tier);
      }
      return { contextExpandedTiers: next };
    }),
  setContextRecallQuery: (q) => set({ contextRecallQuery: q }),
  setContextRecallTier: (tier) => set({ contextRecallTier: tier }),
  setContextGraphSeed: (seed) => set({ contextGraphSeed: seed }),
});
