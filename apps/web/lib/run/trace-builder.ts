/**
 * Flat audit events → nested trace tree (Order 7).
 *
 * Mirrors the LangSmith trace-tree paradigm: each ``agent.invoke``
 * starts a parent run; ``tool.call`` + ``tool.result`` pair under it
 * by ``round`` + ``order``; ``selffork_jr.reply`` is a sibling of the
 * tool calls; ``agent.output`` closes the round; outer events
 * (``session.state``, ``agent.done``, ``error``) are root-level.
 *
 * The builder is pure — easy to test without React.
 */
import type { AuditEvent } from "@/lib/api";

export type TraceNodeKind =
  | "session"
  | "round"
  | "tool_call"
  | "reply"
  | "marker";

export interface TraceNode {
  id: string;
  kind: TraceNodeKind;
  category: string;
  ts: string;
  payload: Record<string, unknown>;
  children: TraceNode[];
  /**
   * Paired ``tool.result`` event for ``tool_call`` nodes, when seen.
   * Lets the renderer show args + result side-by-side in one row.
   */
  pairedResult?: AuditEvent;
}

interface BuildOptions {
  /**
   * When ``true`` the builder treats unknown event categories as
   * markers under the current round (or at the root if no round is
   * active). Default ``true`` — UI is forgiving by design.
   */
  fallbackUnknown?: boolean;
}

interface MutableNode extends Omit<TraceNode, "children"> {
  children: MutableNode[];
}

export function buildTraceTree(
  events: AuditEvent[],
  options: BuildOptions = {},
): TraceNode[] {
  const fallbackUnknown = options.fallbackUnknown ?? true;
  const roots: MutableNode[] = [];
  const roundsByIndex = new Map<number, MutableNode>();
  const pendingToolCalls = new Map<string, MutableNode>();

  let rowIndex = 0;
  for (const ev of events) {
    rowIndex++;
    const id = `${ev.category}-${rowIndex}`;
    const round = numericPayload(ev.payload, "round");
    if (ev.category === "agent.invoke") {
      const node: MutableNode = {
        id,
        kind: "round",
        category: ev.category,
        ts: ev.ts,
        payload: ev.payload,
        children: [],
      };
      roots.push(node);
      if (round !== null) roundsByIndex.set(round, node);
      continue;
    }
    if (ev.category === "agent.output" && round !== null) {
      const parent = roundsByIndex.get(round);
      if (parent) {
        parent.payload = { ...parent.payload, output: ev.payload };
        continue;
      }
    }
    if (ev.category === "tool.call" && round !== null) {
      const tool = stringPayload(ev.payload, "tool");
      const order = numericPayload(ev.payload, "order");
      const key = `${round}-${tool}-${order}`;
      const node: MutableNode = {
        id,
        kind: "tool_call",
        category: ev.category,
        ts: ev.ts,
        payload: ev.payload,
        children: [],
      };
      pendingToolCalls.set(key, node);
      attachToRound(roots, roundsByIndex, round, node);
      continue;
    }
    if (ev.category === "tool.result" && round !== null) {
      const tool = stringPayload(ev.payload, "tool");
      // ``tool.result`` payloads don't carry their own ``order`` (M-7
      // GAP); pair against the most-recent unpaired call for the same
      // (round, tool).
      const matchKey = findCallKey(pendingToolCalls, round, tool);
      if (matchKey !== null) {
        const callNode = pendingToolCalls.get(matchKey)!;
        callNode.pairedResult = ev;
        pendingToolCalls.delete(matchKey);
        continue;
      }
      // No matching call — emit as marker so the row isn't lost.
      const marker: MutableNode = {
        id,
        kind: "marker",
        category: ev.category,
        ts: ev.ts,
        payload: ev.payload,
        children: [],
      };
      attachToRound(roots, roundsByIndex, round, marker);
      continue;
    }
    if (ev.category === "selffork_jr.reply" && round !== null) {
      const node: MutableNode = {
        id,
        kind: "reply",
        category: ev.category,
        ts: ev.ts,
        payload: ev.payload,
        children: [],
      };
      attachToRound(roots, roundsByIndex, round, node);
      continue;
    }
    // Catch-all: marker at root (or under current round if known).
    const node: MutableNode = {
      id,
      kind: "marker",
      category: ev.category,
      ts: ev.ts,
      payload: ev.payload,
      children: [],
    };
    if (round !== null && roundsByIndex.has(round)) {
      roundsByIndex.get(round)!.children.push(node);
    } else if (fallbackUnknown) {
      roots.push(node);
    }
  }
  return roots.map(freeze);
}

function attachToRound(
  roots: MutableNode[],
  roundsByIndex: Map<number, MutableNode>,
  round: number,
  child: MutableNode,
): void {
  const parent = roundsByIndex.get(round);
  if (parent) {
    parent.children.push(child);
  } else {
    roots.push(child);
  }
}

function findCallKey(
  pending: Map<string, MutableNode>,
  round: number,
  tool: string | null,
): string | null {
  if (tool === null) return null;
  const prefix = `${round}-${tool}-`;
  for (const key of pending.keys()) {
    if (key.startsWith(prefix)) return key;
  }
  return null;
}

function freeze(node: MutableNode): TraceNode {
  return {
    ...node,
    children: node.children.map(freeze),
  };
}

function numericPayload(
  payload: Record<string, unknown>,
  key: string,
): number | null {
  const value = payload[key];
  if (typeof value === "number") return value;
  if (typeof value === "string" && value !== "") {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return null;
}

function stringPayload(
  payload: Record<string, unknown>,
  key: string,
): string | null {
  const value = payload[key];
  return typeof value === "string" ? value : null;
}
