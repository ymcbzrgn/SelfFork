import { describe, expect, it } from "vitest";

import {
  CATEGORY_REGISTRY,
  categorySpec,
  summarisePayload,
} from "@/lib/run/event-categories";
import type { AuditEvent } from "@/lib/api";

describe("CATEGORY_REGISTRY coverage", () => {
  // Every audit category emitted by the orchestrator must have a spec.
  // Source of truth: ``packages/shared/src/selffork_shared/audit.py``.
  const REQUIRED = [
    "session.state",
    "runtime.spawn",
    "runtime.health",
    "runtime.stop",
    "sandbox.spawn",
    "sandbox.exec",
    "sandbox.teardown",
    "agent.event",
    "agent.spawn",
    "agent.invoke",
    "agent.output",
    "agent.done",
    "agent.rate_limited",
    "agent.auth_required",
    "agent.spawn_request",
    "agent.spawn_complete",
    "tool.call",
    "tool.result",
    "selffork_jr.reply",
    "mind.note.write",
    "mind.note.supersede",
    "mind.recall.query",
    "mind.compact.run",
    "mind.projection.write",
    "plan.load",
    "plan.save",
    "plan.update",
    "error",
  ];

  for (const cat of REQUIRED) {
    it(`registers ${cat}`, () => {
      expect(CATEGORY_REGISTRY[cat]).toBeDefined();
    });
  }

  it("falls back to a muted spec for unknown categories", () => {
    const spec = categorySpec("totally-new-category");
    expect(spec.label).toBe("totally-new-category");
    expect(spec.accent).toContain("muted");
  });
});

describe("summarisePayload", () => {
  function make(category: string, payload: Record<string, unknown>): AuditEvent {
    return {
      ts: "2026-05-09T18:00:00Z",
      category,
      level: "INFO",
      event: "x",
      payload,
    };
  }

  it("agent.invoke summarises round + binary", () => {
    expect(
      summarisePayload(
        make("agent.invoke", { round: 3, binary: "/x/claude" }),
      ),
    ).toContain("round 3");
  });

  it("tool.result mentions status + error", () => {
    expect(
      summarisePayload(
        make("tool.result", {
          tool: "rotate_to",
          status: "error",
          error: "no provider",
        }),
      ),
    ).toContain("no provider");
  });

  it("falls back to payload key list for unknown category", () => {
    expect(
      summarisePayload(make("custom.category", { a: 1, b: 2 })),
    ).toContain("a");
  });
});
