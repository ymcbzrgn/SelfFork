/**
 * Cockpit store unit tests — Order 5.
 *
 * Verifies all four slices compose into one root store and that each
 * slice's reducers don't accidentally mutate sibling slices.
 */
import { afterEach, describe, expect, it } from "vitest";

import { useCockpitStore } from "@/lib/store";

const initialState = useCockpitStore.getState();

describe("CockpitStore composition", () => {
  afterEach(() => {
    useCockpitStore.setState(initialState, true);
  });

  it("starts on the mission tab", () => {
    expect(useCockpitStore.getState().activeTab).toBe("mission");
  });

  it("setActiveTab updates only the root slice", () => {
    useCockpitStore.getState().setActiveTab("run");
    const s = useCockpitStore.getState();
    expect(s.activeTab).toBe("run");
    expect(s.missionActiveProjectSlug).toBeNull();
    expect(s.runActiveSessionId).toBeNull();
    expect(s.chatActiveBranchId).toBeNull();
    expect(s.contextActiveProjectSlug).toBeNull();
  });

  it("mission slice setters are independent", () => {
    useCockpitStore.getState().setMissionActiveProject("calc");
    useCockpitStore.getState().setMissionSwimlaneMode("session");
    const s = useCockpitStore.getState();
    expect(s.missionActiveProjectSlug).toBe("calc");
    expect(s.missionSwimlaneMode).toBe("session");
    // Switching projects clears the focused card.
    useCockpitStore.getState().setMissionActiveCard("c-1");
    useCockpitStore.getState().setMissionActiveProject("alpha");
    expect(useCockpitStore.getState().missionActiveCardId).toBeNull();
  });

  it("run slice resets last_seq when active session changes", () => {
    useCockpitStore.getState().setRunLastSeq(42);
    expect(useCockpitStore.getState().runLastSeq).toBe(42);
    useCockpitStore.getState().setRunActiveSession("sess-1");
    expect(useCockpitStore.getState().runLastSeq).toBe(0);
  });

  it("run slice setRunFilter only touches the named axis", () => {
    useCockpitStore.getState().setRunFilter("tool", "rotate_to");
    useCockpitStore.getState().setRunFilter("cli", "claude-code");
    const s = useCockpitStore.getState();
    expect(s.runFilterTool).toBe("rotate_to");
    expect(s.runFilterCli).toBe("claude-code");
    expect(s.runFilterCategory).toBeNull();
  });

  it("chat slice token buffer is per-message", () => {
    const { appendChatToken, flushChatTokens } = useCockpitStore.getState();
    appendChatToken("m1", "hello");
    appendChatToken("m1", " world");
    appendChatToken("m2", "other");
    expect(useCockpitStore.getState().chatStreamingTokens).toEqual({
      m1: "hello world",
      m2: "other",
    });
    flushChatTokens("m1");
    expect(useCockpitStore.getState().chatStreamingTokens).toEqual({
      m2: "other",
    });
  });

  it("chat slice setActiveSession clears branch + tokens", () => {
    useCockpitStore.getState().appendChatToken("m1", "x");
    useCockpitStore.getState().setChatActiveBranch("br-1");
    useCockpitStore.getState().setChatActiveSession("sess-2");
    const s = useCockpitStore.getState();
    expect(s.chatActiveSessionId).toBe("sess-2");
    expect(s.chatActiveBranchId).toBeNull();
    expect(s.chatStreamingTokens).toEqual({});
  });

  it("context slice toggles a tier in/out of expanded set", () => {
    const before = useCockpitStore.getState().contextExpandedTiers;
    expect(before.has("working")).toBe(true);
    useCockpitStore.getState().toggleContextTier("working");
    const after = useCockpitStore.getState().contextExpandedTiers;
    expect(after.has("working")).toBe(false);
    useCockpitStore.getState().toggleContextTier("semantic_graph");
    expect(useCockpitStore.getState().contextExpandedTiers.has("semantic_graph")).toBe(true);
  });
});
