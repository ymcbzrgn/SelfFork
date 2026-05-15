/**
 * Trace-tree view — LangSmith-style nested rounds — Order 7.
 *
 * Renders the output of ``buildTraceTree``: each ``round`` node is a
 * collapsible group, with tool calls (paired with their results) and
 * Jr replies as children. Pure render — buildTraceTree owns the data
 * shape, this file just walks it.
 */
"use client";

import type { AuditEvent } from "@/lib/api";
import { buildTraceTree, type TraceNode } from "@/lib/run/trace-builder";
import { categorySpec, summarisePayload } from "@/lib/run/event-categories";
import { cn } from "@/lib/utils";

interface Props {
  events: AuditEvent[];
}

export function TraceTree({ events }: Props) {
  const roots = buildTraceTree(events);
  if (roots.length === 0) {
    return (
      <p className="px-2 py-3 text-xs text-muted-foreground">
        No events yet for this session.
      </p>
    );
  }
  return (
    <div className="space-y-2" data-testid="trace-tree">
      {roots.map((node) => (
        <TraceNodeView key={node.id} node={node} depth={0} />
      ))}
    </div>
  );
}

function TraceNodeView({ node, depth }: { node: TraceNode; depth: number }) {
  const spec = categorySpec(node.category);
  return (
    <div
      style={{ paddingLeft: `${depth * 16}px` }}
      className="border-l border-border/40 pl-2"
      data-testid={`trace-node-${node.category}`}
    >
      <div className="flex items-baseline gap-2 text-xs">
        <span className="font-mono text-[10px] text-muted-foreground">
          {node.ts.slice(11, 19)}
        </span>
        <span className={cn("font-semibold", spec.accent)}>{spec.label}</span>
        <span className="text-muted-foreground">
          — {summarisePayload(syntheticEvent(node))}
        </span>
        {node.pairedResult ? (
          <span
            className={cn(
              "rounded px-1 text-[10px]",
              (node.pairedResult.payload.status as string) === "ok"
                ? "bg-emerald-500/20 text-emerald-300"
                : "bg-rose-500/20 text-rose-300",
            )}
          >
            {(node.pairedResult.payload.status as string) ?? "?"}
          </span>
        ) : null}
      </div>
      {node.children.length > 0 ? (
        <div className="mt-1 space-y-1">
          {node.children.map((c) => (
            <TraceNodeView key={c.id} node={c} depth={depth + 1} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function syntheticEvent(node: TraceNode): AuditEvent {
  // ``summarisePayload`` only reads ``ts``, ``category``, ``payload``;
  // we never feed it an event that needs ``event``/``level`` so an
  // empty placeholder is safe.
  return {
    ts: node.ts,
    category: node.category,
    level: "INFO",
    event: "",
    payload: node.payload,
  };
}
