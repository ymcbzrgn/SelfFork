/**
 * Single component for color-coded session lifecycle states.
 *
 * Centralised so the dashboard's "completed = green" / "paused = amber"
 * mapping stays consistent across paused list, recent table, and
 * session detail header. Adding a new lifecycle state requires
 * updating exactly this file.
 *
 * State strings come from :class:`selffork_orchestrator.lifecycle.states.SessionState`
 * (snake_case enum values). Anything we don't recognize falls back to
 * a neutral muted style — better than crashing on a future state.
 */
import {
  CheckCircle2,
  CircleSlash,
  Clock,
  CloudOff,
  HelpCircle,
  Loader2,
  PauseCircle,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";

export type SessionStateName =
  | "idle"
  | "preparing"
  | "running"
  | "verifying"
  | "completed"
  | "failed"
  | "paused_rate_limit"
  | "torn_down"
  | (string & {});

interface Style {
  className: string;
  icon: LucideIcon;
  label: string;
}

const STYLES: Record<string, Style> = {
  idle: {
    className: "border-border bg-muted text-muted-foreground",
    icon: HelpCircle,
    label: "idle",
  },
  preparing: {
    className: "border-info/40 bg-info/10 text-info",
    icon: Clock,
    label: "preparing",
  },
  running: {
    className: "border-info/40 bg-info/10 text-info",
    icon: Loader2,
    label: "running",
  },
  verifying: {
    className: "border-info/40 bg-info/10 text-info",
    icon: Loader2,
    label: "verifying",
  },
  completed: {
    className: "border-success/40 bg-success/10 text-success",
    icon: CheckCircle2,
    label: "completed",
  },
  failed: {
    className: "border-destructive/40 bg-destructive/10 text-destructive",
    icon: XCircle,
    label: "failed",
  },
  paused_rate_limit: {
    className: "border-warning/40 bg-warning/10 text-warning",
    icon: PauseCircle,
    label: "paused (rate limit)",
  },
  torn_down: {
    className: "border-border bg-secondary text-muted-foreground",
    icon: CircleSlash,
    label: "torn down",
  },
};

export function StatusBadge({
  state,
  className,
  spinningWhenRunning = true,
}: {
  state: SessionStateName | null | undefined;
  className?: string;
  /** When the state is "running" or "verifying", animate the icon. */
  spinningWhenRunning?: boolean;
}) {
  if (!state) {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px]",
          "border-border bg-muted text-muted-foreground",
          className,
        )}
      >
        <CloudOff className="h-3 w-3" />
        <span>unknown</span>
      </span>
    );
  }
  const style = STYLES[state] ?? {
    className: "border-border bg-muted text-muted-foreground",
    icon: HelpCircle,
    label: state,
  };
  const Icon = style.icon;
  const animate =
    spinningWhenRunning && (state === "running" || state === "verifying");
  return (
    <span
      title={state}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium",
        style.className,
        className,
      )}
    >
      <Icon className={cn("h-3 w-3", animate && "animate-spin")} />
      <span>{style.label}</span>
    </span>
  );
}
