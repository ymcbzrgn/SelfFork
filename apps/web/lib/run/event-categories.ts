/**
 * Audit category → renderer registry (Order 7).
 *
 * Maps each of the 22 audit categories the orchestrator emits to a
 * label, accent colour, and short payload preview. Single source of
 * truth so the trace tree, waterfall, and filter chip surfaces stay
 * in sync. ``unknown`` is a sentinel for forward-compat (new
 * categories surface as muted markers instead of disappearing).
 */
import type { AuditEvent } from "@/lib/api";

export type EventGroup = "state" | "lifecycle" | "agent" | "tool" | "mind" | "plan";

export interface CategorySpec {
  label: string;
  group: EventGroup;
  accent: string;
}

export const CATEGORY_REGISTRY: Record<string, CategorySpec> = {
  // state
  "session.state": {
    label: "Session state",
    group: "state",
    accent: "text-blue-300",
  },
  // lifecycle (runtime/sandbox)
  "runtime.spawn": {
    label: "Runtime spawn",
    group: "lifecycle",
    accent: "text-zinc-400",
  },
  "runtime.health": {
    label: "Runtime health",
    group: "lifecycle",
    accent: "text-zinc-400",
  },
  "runtime.stop": {
    label: "Runtime stop",
    group: "lifecycle",
    accent: "text-zinc-400",
  },
  "sandbox.spawn": {
    label: "Sandbox spawn",
    group: "lifecycle",
    accent: "text-zinc-400",
  },
  "sandbox.exec": {
    label: "Sandbox exec",
    group: "lifecycle",
    accent: "text-zinc-400",
  },
  "sandbox.teardown": {
    label: "Sandbox teardown",
    group: "lifecycle",
    accent: "text-zinc-400",
  },
  // agent
  "agent.event": {
    // Pre-round-loop architecture left this category in shared/audit
    // for backwards compat — old session JSONL files still surface it.
    label: "Agent event (legacy)",
    group: "agent",
    accent: "text-purple-200",
  },
  "agent.spawn": {
    label: "Agent spawn (legacy)",
    group: "agent",
    accent: "text-purple-300",
  },
  "agent.invoke": {
    label: "Agent invoke",
    group: "agent",
    accent: "text-purple-300",
  },
  "agent.output": {
    label: "Agent output",
    group: "agent",
    accent: "text-emerald-300",
  },
  "agent.done": {
    label: "Agent done",
    group: "agent",
    accent: "text-emerald-400",
  },
  "agent.rate_limited": {
    label: "Rate limited",
    group: "agent",
    accent: "text-amber-300",
  },
  "agent.auth_required": {
    label: "Auth required",
    group: "agent",
    accent: "text-rose-300",
  },
  "agent.spawn_request": {
    label: "Spawn request",
    group: "agent",
    accent: "text-purple-200",
  },
  "agent.spawn_complete": {
    label: "Spawn complete",
    group: "agent",
    accent: "text-purple-200",
  },
  // tool
  "tool.call": {
    label: "Tool call",
    group: "tool",
    accent: "text-sky-300",
  },
  "tool.result": {
    label: "Tool result",
    group: "tool",
    accent: "text-sky-200",
  },
  "selffork_jr.reply": {
    label: "Jr reply",
    group: "tool",
    accent: "text-foreground",
  },
  // mind
  "mind.note.write": {
    label: "Mind note write",
    group: "mind",
    accent: "text-orange-300",
  },
  "mind.note.supersede": {
    label: "Mind note supersede",
    group: "mind",
    accent: "text-orange-300",
  },
  "mind.recall.query": {
    label: "Mind recall",
    group: "mind",
    accent: "text-orange-300",
  },
  "mind.compact.run": {
    label: "Mind compact",
    group: "mind",
    accent: "text-orange-300",
  },
  "mind.projection.write": {
    label: "Mind projection",
    group: "mind",
    accent: "text-orange-300",
  },
  // plan
  "plan.load": {
    label: "Plan load",
    group: "plan",
    accent: "text-yellow-300",
  },
  "plan.save": {
    label: "Plan save",
    group: "plan",
    accent: "text-yellow-300",
  },
  "plan.update": {
    label: "Plan update",
    group: "plan",
    accent: "text-yellow-300",
  },
  // error
  error: {
    label: "Error",
    group: "agent",
    accent: "text-rose-400",
  },
};

export function categorySpec(category: string): CategorySpec {
  return (
    CATEGORY_REGISTRY[category] ?? {
      label: category,
      group: "lifecycle",
      accent: "text-muted-foreground",
    }
  );
}

export function summarisePayload(ev: AuditEvent): string {
  const p = ev.payload;
  switch (ev.category) {
    case "agent.invoke":
      return `round ${p.round} · ${(p.binary as string) ?? "?"}`;
    case "agent.output":
      return `round ${p.round} · exit ${p.exit_code} · ${p.output_chars}c`;
    case "tool.call":
      return `${p.tool} · order ${p.order ?? "?"}`;
    case "tool.result":
      return `${p.tool} · ${p.status}${p.error ? ` · ${p.error}` : ""}`;
    case "selffork_jr.reply":
      return `${p.chars ?? ""}c`;
    case "session.state":
      return `${p.from ?? "?"} → ${p.to ?? "?"}`;
    case "agent.rate_limited":
      return `${p.kind ?? "?"} · ${p.reason ?? "?"}`;
    case "agent.done":
      return `${p.reason ?? ""} · ${p.rounds ?? 0} rounds`;
    default:
      return Object.keys(p).join(", ");
  }
}
