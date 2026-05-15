/**
 * Fleet / Providers / Body slice unit tests (M5 — ADR-005 §M5-A/D/E).
 *
 * Exercises each slice's reducers in isolation to keep regressions caught
 * before they reach the cockpit pages.
 */
import { afterEach, describe, expect, it } from "vitest";

import {
  useCockpitStore,
  type BodyEvent,
  type BodySession,
  type DaemonView,
  type ProviderState,
} from "@/lib/store";

const initialState = useCockpitStore.getState();

afterEach(() => {
  useCockpitStore.setState(initialState, true);
});

describe("FleetSlice", () => {
  const daemon: DaemonView = {
    machine_id: "work-ubuntu",
    hostname: "work.local",
    location_tier: "work",
    version: "0.5.0",
    online: true,
    latency_ms: 18,
    last_heartbeat: "2026-05-10T12:00:00Z",
    registered_at: "2026-05-10T11:00:00Z",
    snapper_clis: ["claude"],
  };

  it("setFleetDaemons replaces the list", () => {
    useCockpitStore.getState().setFleetDaemons([daemon]);
    expect(useCockpitStore.getState().fleetDaemons).toHaveLength(1);
  });

  it("upsertFleetDaemon inserts when missing", () => {
    useCockpitStore.getState().upsertFleetDaemon(daemon);
    expect(useCockpitStore.getState().fleetDaemons[0].machine_id).toBe(
      "work-ubuntu",
    );
  });

  it("upsertFleetDaemon updates in place when present", () => {
    useCockpitStore.getState().upsertFleetDaemon(daemon);
    useCockpitStore.getState().upsertFleetDaemon({
      ...daemon,
      online: false,
      latency_ms: null,
    });
    const state = useCockpitStore.getState().fleetDaemons;
    expect(state).toHaveLength(1);
    expect(state[0].online).toBe(false);
  });

  it("setFleetCurrentMachine cycles between values", () => {
    useCockpitStore.getState().setFleetCurrentMachine("work-ubuntu");
    expect(useCockpitStore.getState().fleetCurrentMachineId).toBe("work-ubuntu");
    useCockpitStore.getState().setFleetCurrentMachine(null);
    expect(useCockpitStore.getState().fleetCurrentMachineId).toBeNull();
  });
});

describe("ProvidersSlice", () => {
  it("seeds five providers in disconnected state", () => {
    const providers = useCockpitStore.getState().providers;
    expect(Object.keys(providers)).toEqual([
      "claude_pro",
      "codex",
      "gemini",
      "opencode",
      "mmx",
    ]);
    for (const provider of Object.values(providers)) {
      expect(provider.status).toBe("disconnected");
    }
  });

  it("setProviderState updates a single provider", () => {
    useCockpitStore.getState().setProviderState("codex", {
      status: "connected",
      expires_at: "2026-12-01T00:00:00Z",
    });
    const provider = useCockpitStore.getState().providers["codex"];
    expect(provider.status).toBe("connected");
    expect(provider.expires_at).toBe("2026-12-01T00:00:00Z");
    // Other providers unaffected.
    expect(useCockpitStore.getState().providers["gemini"].status).toBe(
      "disconnected",
    );
  });

  it("setProviders bulk-replaces a subset", () => {
    const update: ProviderState[] = [
      {
        name: "gemini",
        status: "connected",
        expires_at: null,
        last_sign_in: "2026-05-10T13:00:00Z",
        last_error: null,
      },
    ];
    useCockpitStore.getState().setProviders(update);
    expect(useCockpitStore.getState().providers["gemini"].status).toBe(
      "connected",
    );
  });

  it("setSignInSession round-trips", () => {
    useCockpitStore.getState().setSignInSession("session-abc");
    expect(useCockpitStore.getState().signInSessionId).toBe("session-abc");
  });
});

describe("BodySlice", () => {
  const session: BodySession = {
    session_id: "s1",
    driver: "web",
    started_at: "2026-05-10T12:00:00Z",
    killed: false,
    last_activity: "2026-05-10T12:01:00Z",
  };
  const baseEvent: Omit<BodyEvent, "id" | "ts"> = {
    category: "body.action.executed",
    session_id: "s1",
    risk_tier: "T1",
    action_type: "click",
    duration_ms: 120,
    warden_decision: "allow",
    warden_reason: null,
    before_screenshot_ref: null,
    after_screenshot_ref: null,
    payload: {},
  };

  it("setBodySessions replaces the list", () => {
    useCockpitStore.getState().setBodySessions([session]);
    expect(useCockpitStore.getState().bodySessions).toHaveLength(1);
  });

  it("pushBodyEvent appends in order", () => {
    useCockpitStore.getState().pushBodyEvent({
      ...baseEvent,
      id: "e1",
      ts: "2026-05-10T12:00:00Z",
    });
    useCockpitStore.getState().pushBodyEvent({
      ...baseEvent,
      id: "e2",
      ts: "2026-05-10T12:00:01Z",
    });
    const events = useCockpitStore.getState().bodyEvents;
    expect(events.map((e) => e.id)).toEqual(["e1", "e2"]);
  });

  it("pushBodyEvent caps buffer at 100", () => {
    for (let i = 0; i < 110; i += 1) {
      useCockpitStore.getState().pushBodyEvent({
        ...baseEvent,
        id: `e${i}`,
        ts: `2026-05-10T12:00:${i.toString().padStart(2, "0")}Z`,
      });
    }
    const events = useCockpitStore.getState().bodyEvents;
    expect(events).toHaveLength(100);
    expect(events[0].id).toBe("e10");
    expect(events[99].id).toBe("e109");
  });

  it("pushPermissionPrompt is idempotent on request_id", () => {
    const prompt = {
      request_id: "r1",
      session_id: "s1",
      action_type: "shell_exec",
      risk_tier: "T2" as const,
      target_uri: null,
      args_summary: {},
      requested_at: "2026-05-10T12:00:00Z",
    };
    useCockpitStore.getState().pushPermissionPrompt(prompt);
    useCockpitStore.getState().pushPermissionPrompt(prompt);
    expect(useCockpitStore.getState().bodyPrompts).toHaveLength(1);
  });

  it("resolvePermissionPrompt removes by id", () => {
    useCockpitStore.getState().pushPermissionPrompt({
      request_id: "r1",
      session_id: "s1",
      action_type: "shell_exec",
      risk_tier: "T2",
      target_uri: null,
      args_summary: {},
      requested_at: "2026-05-10T12:00:00Z",
    });
    useCockpitStore.getState().resolvePermissionPrompt("r1");
    expect(useCockpitStore.getState().bodyPrompts).toEqual([]);
  });

  it("setBodyLatency records p50/p95", () => {
    useCockpitStore.getState().setBodyLatency(820, 1850);
    expect(useCockpitStore.getState().bodyLatencyP50Ms).toBe(820);
    expect(useCockpitStore.getState().bodyLatencyP95Ms).toBe(1850);
  });
});
