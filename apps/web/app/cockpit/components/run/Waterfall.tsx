/**
 * Waterfall view — AgentOps-style gantt — Order 7.
 *
 * Plain HTML/CSS bars (no D3/visx) so the cockpit's bundle stays
 * thin. The bar width is proportional to ``durationMs`` over the
 * total session span; very-short events still get a 2px floor so
 * they're clickable.
 */
"use client";

import type { AuditEvent } from "@/lib/api";
import { buildWaterfall } from "@/lib/run/waterfall-builder";
import { categorySpec } from "@/lib/run/event-categories";
import { cn } from "@/lib/utils";

interface Props {
  events: AuditEvent[];
}

const MIN_WIDTH_PX = 2;

export function Waterfall({ events }: Props) {
  const rows = buildWaterfall(events);
  if (rows.length === 0) {
    return (
      <p className="px-2 py-3 text-xs text-muted-foreground">
        No events yet for this session.
      </p>
    );
  }
  const total = Math.max(
    1,
    rows[rows.length - 1].startMs + (rows[rows.length - 1].durationMs || 1),
  );
  return (
    <div className="space-y-1" data-testid="waterfall">
      {rows.map((row) => {
        const left = (row.startMs / total) * 100;
        const width = Math.max((row.durationMs / total) * 100, 0);
        const spec = categorySpec(row.category);
        return (
          <div
            key={row.id}
            className="flex items-center gap-2 text-xs"
            data-testid={`waterfall-row-${row.category}`}
          >
            <span className="w-32 shrink-0 truncate text-muted-foreground">
              {row.label}
            </span>
            <div className="relative h-3 flex-1 rounded bg-muted/40">
              <div
                className={cn(
                  "absolute top-0 h-full rounded",
                  spec.accent.replace("text-", "bg-"),
                )}
                style={{
                  left: `${left}%`,
                  width: `max(${width}%, ${MIN_WIDTH_PX}px)`,
                }}
              />
            </div>
            <span className="w-16 shrink-0 text-right font-mono text-[10px] text-muted-foreground">
              {Math.round(row.durationMs)}ms
            </span>
          </div>
        );
      })}
    </div>
  );
}
