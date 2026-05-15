/**
 * Single audit-event row — shared by AuditStream and TraceTree.
 *
 * Pulls the label + accent + payload summary from
 * ``CATEGORY_REGISTRY``. Unknown categories fall back to a muted
 * marker so the UI never silently drops a frame.
 */
"use client";

import type { AuditEvent } from "@/lib/api";
import { categorySpec, summarisePayload } from "@/lib/run/event-categories";
import { cn } from "@/lib/utils";

export function EventRow({ event }: { event: AuditEvent }) {
  const spec = categorySpec(event.category);
  return (
    <div
      className="flex items-baseline gap-2 px-2 py-1 text-xs"
      data-testid={`event-row-${event.category}`}
    >
      <time className="font-mono text-[10px] text-muted-foreground">
        {event.ts.slice(11, 19)}
      </time>
      <span className={cn("font-semibold", spec.accent)}>{spec.label}</span>
      <span className="text-muted-foreground">— {summarisePayload(event)}</span>
    </div>
  );
}
