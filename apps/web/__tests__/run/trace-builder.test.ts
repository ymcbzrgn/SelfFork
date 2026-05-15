/**
 * Pure unit tests for ``buildTraceTree`` — Order 7.
 */
import { describe, expect, it } from "vitest";

import type { AuditEvent } from "@/lib/api";
import { buildTraceTree } from "@/lib/run/trace-builder";

function ev(
  category: string,
  payload: Record<string, unknown>,
  ts = "2026-05-09T18:00:00.000Z",
): AuditEvent {
  return { ts, category, level: "INFO", event: "test", payload };
}

describe("buildTraceTree", () => {
  it("returns an empty array for no events", () => {
    expect(buildTraceTree([])).toEqual([]);
  });

  it("nests tool calls under the round invoke", () => {
    const tree = buildTraceTree([
      ev("agent.invoke", { round: 0, binary: "/x/claude" }),
      ev("tool.call", { round: 0, tool: "rotate_to", order: 0 }),
      ev("tool.result", {
        round: 0,
        tool: "rotate_to",
        status: "ok",
      }),
      ev("selffork_jr.reply", { round: 0, chars: 12 }),
      ev("agent.output", { round: 0, exit_code: 0, output_chars: 100 }),
    ]);
    expect(tree).toHaveLength(1);
    const round = tree[0];
    expect(round.kind).toBe("round");
    // Tool call + reply children (output is folded into the round payload).
    expect(round.children.map((c) => c.kind)).toEqual([
      "tool_call",
      "reply",
    ]);
    expect(round.children[0].pairedResult).toBeDefined();
  });

  it("emits a marker when a tool.result has no matching call", () => {
    const tree = buildTraceTree([
      ev("agent.invoke", { round: 1, binary: "/x" }),
      ev("tool.result", {
        round: 1,
        tool: "rotate_to",
        status: "ok",
      }),
    ]);
    const round = tree[0];
    expect(round.children).toHaveLength(1);
    expect(round.children[0].kind).toBe("marker");
  });

  it("orphan tool calls (no round) surface as root markers", () => {
    // Production never emits a tool.call without a round — the
    // orchestrator's lifecycle only invokes the registry inside an
    // active round. The builder surfaces them as root markers so
    // corrupted audit logs (older format, partial writes) stay
    // visible to the operator instead of disappearing.
    const tree = buildTraceTree([
      ev("tool.call", { tool: "x", order: 0 }),
    ]);
    expect(tree).toHaveLength(1);
    expect(tree[0].kind).toBe("marker");
    expect(tree[0].category).toBe("tool.call");
  });

  it("places unknown categories at the root by default", () => {
    const tree = buildTraceTree([
      ev("session.state", { from: "idle", to: "preparing" }),
      ev("agent.done", { reason: "done", rounds: 0 }),
    ]);
    expect(tree).toHaveLength(2);
    expect(tree.every((n) => n.kind === "marker")).toBe(true);
  });

  it("paired round + multiple tool calls keeps order", () => {
    const tree = buildTraceTree([
      ev("agent.invoke", { round: 0, binary: "/x" }),
      ev("tool.call", { round: 0, tool: "a", order: 0 }),
      ev("tool.call", { round: 0, tool: "b", order: 1 }),
      ev("tool.result", { round: 0, tool: "a", status: "ok" }),
      ev("tool.result", { round: 0, tool: "b", status: "ok" }),
    ]);
    const round = tree[0];
    expect(round.children).toHaveLength(2);
    expect(round.children[0].pairedResult).toBeDefined();
    expect(round.children[1].pairedResult).toBeDefined();
  });

  it("pairs same-tool repeated calls in FIFO insertion order", () => {
    // Order 7 audit Finding HIGH-3: tool.result lacks ``order``; the
    // builder must rely on insertion order to keep multi-call same-
    // round flows correct. This test pins that contract so a future
    // refactor (parallel tool dispatch) can't silently re-order
    // pairings.
    const tree = buildTraceTree([
      ev("agent.invoke", { round: 0, binary: "/x" }),
      ev("tool.call", { round: 0, tool: "mind_recall", order: 0, args: { q: "first" } }),
      ev("tool.call", { round: 0, tool: "mind_recall", order: 1, args: { q: "second" } }),
      ev("tool.result", { round: 0, tool: "mind_recall", status: "ok", payload_keys: ["one"] }),
      ev("tool.result", { round: 0, tool: "mind_recall", status: "ok", payload_keys: ["two"] }),
    ]);
    const round = tree[0];
    expect(round.children).toHaveLength(2);
    // First call paired with first result; second with second.
    const firstCall = round.children[0];
    const secondCall = round.children[1];
    expect((firstCall.payload.args as { q: string }).q).toBe("first");
    expect(firstCall.pairedResult?.payload.payload_keys).toEqual(["one"]);
    expect((secondCall.payload.args as { q: string }).q).toBe("second");
    expect(secondCall.pairedResult?.payload.payload_keys).toEqual(["two"]);
  });
});
