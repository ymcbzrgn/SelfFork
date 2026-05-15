/**
 * Mission tab slice (Order 5 placeholder, Order 6 fills the rest).
 *
 * Keeps only what the tab shell + drawer need to render before
 * Order 6 lands the swimlane kanban.
 */
import type { StateCreator } from "zustand";

import type { CockpitStore } from "./index";

export type SwimlaneMode = "status" | "session";

export interface MissionSlice {
  missionActiveProjectSlug: string | null;
  missionActiveCardId: string | null;
  missionSwimlaneMode: SwimlaneMode;
  missionFilterCli: string | null;
  setMissionActiveProject: (slug: string | null) => void;
  setMissionActiveCard: (id: string | null) => void;
  setMissionSwimlaneMode: (mode: SwimlaneMode) => void;
  setMissionFilterCli: (cli: string | null) => void;
}

export const createMissionSlice: StateCreator<
  CockpitStore,
  [["zustand/devtools", never]],
  [],
  MissionSlice
> = (set) => ({
  missionActiveProjectSlug: null,
  missionActiveCardId: null,
  missionSwimlaneMode: "status",
  missionFilterCli: null,
  setMissionActiveProject: (slug) =>
    set({ missionActiveProjectSlug: slug, missionActiveCardId: null }),
  setMissionActiveCard: (id) => set({ missionActiveCardId: id }),
  setMissionSwimlaneMode: (mode) => set({ missionSwimlaneMode: mode }),
  setMissionFilterCli: (cli) => set({ missionFilterCli: cli }),
});
