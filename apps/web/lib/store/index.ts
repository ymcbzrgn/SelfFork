/**
 * Cockpit Zustand root store — Order 5.
 *
 * Four independent slices (mission / run / chat / context) share a
 * single store so cross-slice selectors are cheap and the React
 * Devtools panel groups the cockpit state under one root.
 *
 * Each slice is pure UI state — server data lives in TanStack Query
 * (see ``lib/query.ts``). The split keeps WS-driven cache updates and
 * UI ephemeral state cleanly separated (M-2 architectural decision).
 */
import { create, type StateCreator } from "zustand";
import { devtools } from "zustand/middleware";

import { createMissionSlice, type MissionSlice } from "./mission-slice";
import { createRunSlice, type RunSlice } from "./run-slice";
import { createChatSlice, type ChatSlice } from "./chat-slice";
import {
  createContextSlice,
  type ContextSlice,
  type MindTier,
} from "./context-slice";
import { createFleetSlice, type FleetSlice } from "./fleet-slice";
import { createProvidersSlice, type ProvidersSlice } from "./providers-slice";
import { createBodySlice, type BodySlice } from "./body-slice";

export type CockpitTab =
  | "mission"
  | "run"
  | "chat"
  | "context"
  | "fleet"
  | "providers"
  | "body";

export interface RootSlice {
  activeTab: CockpitTab;
  setActiveTab: (tab: CockpitTab) => void;
}

export type CockpitStore = RootSlice &
  MissionSlice &
  RunSlice &
  ChatSlice &
  ContextSlice &
  FleetSlice &
  ProvidersSlice &
  BodySlice;

const createRootSlice: StateCreator<
  CockpitStore,
  [["zustand/devtools", never]],
  [],
  RootSlice
> = (set) => ({
  activeTab: "mission",
  setActiveTab: (tab) => set({ activeTab: tab }),
});

export const useCockpitStore = create<CockpitStore>()(
  devtools(
    (...a) => ({
      ...createRootSlice(...a),
      ...createMissionSlice(...a),
      ...createRunSlice(...a),
      ...createChatSlice(...a),
      ...createContextSlice(...a),
      ...createFleetSlice(...a),
      ...createProvidersSlice(...a),
      ...createBodySlice(...a),
    }),
    { name: "selffork-cockpit" },
  ),
);

export type {
  BodySlice,
  ChatSlice,
  ContextSlice,
  FleetSlice,
  MindTier,
  MissionSlice,
  ProvidersSlice,
  RunSlice,
};
