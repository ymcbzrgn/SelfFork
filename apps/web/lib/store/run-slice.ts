/**
 * Run tab slice — Order 5 placeholder + Order 7's filter/paradigm fields.
 */
import type { StateCreator } from "zustand";

import type { CockpitStore } from "./index";

export type RunParadigm = "trace" | "waterfall";

export interface RunSlice {
  runActiveSessionId: string | null;
  runParadigm: RunParadigm;
  runFilterTool: string | null;
  runFilterCli: string | null;
  runFilterCategory: string | null;
  runSearchQuery: string;
  runLastSeq: number;
  setRunActiveSession: (id: string | null) => void;
  setRunParadigm: (p: RunParadigm) => void;
  setRunFilter: (
    key: "tool" | "cli" | "category",
    value: string | null,
  ) => void;
  setRunSearchQuery: (q: string) => void;
  setRunLastSeq: (seq: number) => void;
}

export const createRunSlice: StateCreator<
  CockpitStore,
  [["zustand/devtools", never]],
  [],
  RunSlice
> = (set) => ({
  runActiveSessionId: null,
  runParadigm: "trace",
  runFilterTool: null,
  runFilterCli: null,
  runFilterCategory: null,
  runSearchQuery: "",
  runLastSeq: 0,
  setRunActiveSession: (id) =>
    set({ runActiveSessionId: id, runLastSeq: 0 }),
  setRunParadigm: (p) => set({ runParadigm: p }),
  setRunFilter: (key, value) => {
    if (key === "tool") set({ runFilterTool: value });
    if (key === "cli") set({ runFilterCli: value });
    if (key === "category") set({ runFilterCategory: value });
  },
  setRunSearchQuery: (q) => set({ runSearchQuery: q }),
  setRunLastSeq: (seq) => set({ runLastSeq: seq }),
});
