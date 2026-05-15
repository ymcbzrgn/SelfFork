/**
 * Swimlane mode toggle — Mission tab — Order 6.
 *
 * Switches the kanban between status columns and per-session rows.
 * Tiny segmented control — keeps to two states for now (Linear-style
 * "Group by" expansion is M5+).
 */
"use client";

import { useCockpitStore } from "@/lib/store";
import { cn } from "@/lib/utils";

const MODES: Array<{ value: "status" | "session"; label: string }> = [
  { value: "status", label: "By status" },
  { value: "session", label: "By session" },
];

export function SwimlaneToggle() {
  const mode = useCockpitStore((s) => s.missionSwimlaneMode);
  const setMode = useCockpitStore((s) => s.setMissionSwimlaneMode);
  return (
    <div
      role="radiogroup"
      aria-label="Mission view mode"
      className="inline-flex rounded-md border border-border/60 bg-card text-xs"
      data-testid="mission-swimlane-toggle"
    >
      {MODES.map((m) => (
        <button
          key={m.value}
          role="radio"
          aria-checked={mode === m.value}
          type="button"
          onClick={() => setMode(m.value)}
          className={cn(
            "px-3 py-1 transition-colors",
            mode === m.value
              ? "bg-primary/20 text-foreground"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {m.label}
        </button>
      ))}
    </div>
  );
}
