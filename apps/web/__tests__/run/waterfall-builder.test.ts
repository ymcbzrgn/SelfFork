import { describe, expect, it } from "vitest";

import type { AuditEvent } from "@/lib/api";
import { buildWaterfall } from "@/lib/run/waterfall-builder";

function ev(category: string, ts: string, payload: Record<string, unknown> = {}): AuditEvent {
  return { ts, category, level: "INFO", event: "test", payload };
}

describe("buildWaterfall", () => {
  it("returns empty for no events", () => {
    expect(buildWaterfall([])).toEqual([]);
  });

  it("computes startMs relative to the first event (cursor-based)", () => {
    const rows = buildWaterfall([
      ev("agent.invoke", "2026-05-09T18:00:00.000Z", { round: 0 }),
      ev("agent.output", "2026-05-09T18:00:01.500Z", { round: 0 }),
    ]);
    expect(rows[0].startMs).toBe(0);
    expect(rows[0].durationMs).toBe(1500);
    expect(rows[1].startMs).toBe(1500);
    expect(rows[1].durationMs).toBe(0);
    expect(rows[0].isClampedSleep).toBe(false);
  });

  it("clamps long agent.rate_limited cooldowns to keep the canvas readable", () => {
    // Order 7 audit fix: 5 h sleep used to consume the whole canvas;
    // now we cap the bar at ~60 s and flag the row.
    const rows = buildWaterfall([
      ev("agent.invoke", "2026-05-09T18:00:00.000Z", { round: 0 }),
      ev("agent.rate_limited", "2026-05-09T18:00:01.000Z", {
        kind: "five_hour",
      }),
      ev("session.state", "2026-05-09T23:00:01.000Z", {
        from: "paused_rate_limit",
        to: "running",
      }),
    ]);
    expect(rows[1].category).toBe("agent.rate_limited");
    expect(rows[1].isClampedSleep).toBe(true);
    expect(rows[1].rawDurationMs).toBe(5 * 60 * 60 * 1000); // 5 h raw
    expect(rows[1].durationMs).toBe(60_000); // 60 s clamped
    // Subsequent rows shift down to the clamp window — total span
    // stays bounded.
    expect(rows[2].startMs).toBe(1_000 + 60_000);
  });

  it("labels rounds and tool calls", () => {
    const rows = buildWaterfall([
      ev("agent.invoke", "2026-05-09T18:00:00.000Z", { round: 7 }),
      ev("tool.call", "2026-05-09T18:00:01.000Z", {
        tool: "rotate_to",
        round: 7,
      }),
    ]);
    expect(rows[0].label).toBe("Round 7");
    expect(rows[1].label).toContain("rotate_to");
    expect(rows[0].groupKey).toBe("round-7");
  });

  it("session.state rows fall back to a session group key", () => {
    const rows = buildWaterfall([
      ev("session.state", "2026-05-09T18:00:00Z", {
        from: "idle",
        to: "preparing",
      }),
    ]);
    expect(rows[0].groupKey).toBe("session");
    expect(rows[0].label).toContain("preparing");
  });
});
