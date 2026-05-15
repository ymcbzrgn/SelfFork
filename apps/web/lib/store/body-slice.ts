/**
 * Body slice (M5 — ADR-005 §M5-D).
 *
 * Live state for the cockpit's Body tab — active sessions, last 100 audit
 * events scoped to ``body.*`` categories, screenshot timeline pointers,
 * vision latency rolling stats. WS deltas (``body_action`` /
 * ``body_observation``) update the slice; REST snapshots fill the buffer
 * after a reconnect.
 */
import type { StateCreator } from "zustand";

import type { CockpitStore } from "./index";

export type RiskTier = "T0" | "T1" | "T2" | "T3";
export type WardenDecision = "allow" | "deny" | "approved" | "killed";

export interface BodyEvent {
  id: string;
  ts: string;
  category: string;
  session_id: string;
  risk_tier: RiskTier | null;
  action_type: string | null;
  duration_ms: number | null;
  warden_decision: WardenDecision | null;
  warden_reason: string | null;
  before_screenshot_ref: string | null;
  after_screenshot_ref: string | null;
  payload: Record<string, unknown>;
}

export interface BodySession {
  session_id: string;
  driver: string;
  started_at: string;
  killed: boolean;
  last_activity: string;
}

export interface PermissionPrompt {
  request_id: string;
  session_id: string;
  action_type: string;
  risk_tier: RiskTier;
  target_uri: string | null;
  args_summary: Record<string, unknown>;
  requested_at: string;
}

const BODY_BUFFER_LIMIT = 100;

export interface BodySlice {
  bodySessions: BodySession[];
  bodyEvents: BodyEvent[];
  bodyPrompts: PermissionPrompt[];
  bodyLatencyP50Ms: number | null;
  bodyLatencyP95Ms: number | null;
  setBodySessions: (sessions: BodySession[]) => void;
  pushBodyEvent: (event: BodyEvent) => void;
  pushPermissionPrompt: (prompt: PermissionPrompt) => void;
  resolvePermissionPrompt: (request_id: string) => void;
  setBodyLatency: (p50: number | null, p95: number | null) => void;
}

export const createBodySlice: StateCreator<
  CockpitStore,
  [["zustand/devtools", never]],
  [],
  BodySlice
> = (set) => ({
  bodySessions: [],
  bodyEvents: [],
  bodyPrompts: [],
  bodyLatencyP50Ms: null,
  bodyLatencyP95Ms: null,
  setBodySessions: (sessions) =>
    set({ bodySessions: sessions }, false, "body/setSessions"),
  pushBodyEvent: (event) =>
    set(
      (state) => {
        const next = [...state.bodyEvents, event];
        if (next.length > BODY_BUFFER_LIMIT) {
          next.splice(0, next.length - BODY_BUFFER_LIMIT);
        }
        return { bodyEvents: next };
      },
      false,
      "body/pushEvent",
    ),
  pushPermissionPrompt: (prompt) =>
    set(
      (state) => {
        if (state.bodyPrompts.some((p) => p.request_id === prompt.request_id)) {
          return state;
        }
        return { bodyPrompts: [...state.bodyPrompts, prompt] };
      },
      false,
      "body/pushPrompt",
    ),
  resolvePermissionPrompt: (request_id) =>
    set(
      (state) => ({
        bodyPrompts: state.bodyPrompts.filter(
          (p) => p.request_id !== request_id,
        ),
      }),
      false,
      "body/resolvePrompt",
    ),
  setBodyLatency: (p50, p95) =>
    set(
      { bodyLatencyP50Ms: p50, bodyLatencyP95Ms: p95 },
      false,
      "body/setLatency",
    ),
});
