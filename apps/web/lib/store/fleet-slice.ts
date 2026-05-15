/**
 * Fleet slice (M5 — ADR-005 §M5-A).
 *
 * Tracks the body-daemon fleet: which machines are registered, who's online,
 * the current machine the operator is "on" (used by the location-aware
 * slider in MissionSlice's threshold logic). Server data lives in TanStack
 * Query under the ``fleet`` key; this slice only owns the cross-tab UI
 * ephemeral state (currently selected machine).
 */
import type { StateCreator } from "zustand";

import type { CockpitStore } from "./index";

export type LocationTier = "home" | "work" | "auto";

export interface DaemonView {
  machine_id: string;
  hostname: string;
  location_tier: LocationTier;
  version: string;
  online: boolean;
  latency_ms: number | null;
  last_heartbeat: string | null;
  registered_at: string;
  snapper_clis: string[];
}

export interface FleetSlice {
  fleetCurrentMachineId: string | null;
  fleetDaemons: DaemonView[];
  setFleetCurrentMachine: (id: string | null) => void;
  setFleetDaemons: (daemons: DaemonView[]) => void;
  upsertFleetDaemon: (daemon: DaemonView) => void;
}

export const createFleetSlice: StateCreator<
  CockpitStore,
  [["zustand/devtools", never]],
  [],
  FleetSlice
> = (set) => ({
  fleetCurrentMachineId: null,
  fleetDaemons: [],
  setFleetCurrentMachine: (id) =>
    set({ fleetCurrentMachineId: id }, false, "fleet/setCurrentMachine"),
  setFleetDaemons: (daemons) =>
    set({ fleetDaemons: daemons }, false, "fleet/setDaemons"),
  upsertFleetDaemon: (daemon) =>
    set(
      (state) => {
        const existing = state.fleetDaemons.findIndex(
          (d) => d.machine_id === daemon.machine_id,
        );
        if (existing === -1) {
          return { fleetDaemons: [...state.fleetDaemons, daemon] };
        }
        const next = [...state.fleetDaemons];
        next[existing] = daemon;
        return { fleetDaemons: next };
      },
      false,
      "fleet/upsertDaemon",
    ),
});
