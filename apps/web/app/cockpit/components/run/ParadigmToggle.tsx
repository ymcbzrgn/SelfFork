/**
 * Trace-tree ↔ Waterfall toggle — Order 7.
 *
 * Mirror of the Mission tab's swimlane toggle pattern — minimal
 * segmented control wired to ``runParadigm`` in the cockpit store.
 */
"use client";

import { useCockpitStore } from "@/lib/store";
import { cn } from "@/lib/utils";

const MODES: Array<{ value: "trace" | "waterfall"; label: string }> = [
  { value: "trace", label: "Trace" },
  { value: "waterfall", label: "Waterfall" },
];

export function ParadigmToggle() {
  const mode = useCockpitStore((s) => s.runParadigm);
  const setMode = useCockpitStore((s) => s.setRunParadigm);
  return (
    <div
      role="radiogroup"
      aria-label="Run paradigm"
      className="inline-flex rounded-md border border-border/60 bg-card text-xs"
      data-testid="run-paradigm-toggle"
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
