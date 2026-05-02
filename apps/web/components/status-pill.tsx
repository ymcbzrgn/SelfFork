/**
 * Fixed-width color-keyed pill (Skyvern pattern, ``h-6 w-fit`` instead
 * of Skyvern's ``h-7 w-24`` so we can fit it on dense cards). The
 * column an item lives in IS the status — we surface it as a pill so
 * the eye can scan a column at a glance.
 *
 * Pairs with :class:`StatusDot` for the cross-pillar status grammar:
 * the dot animates while transient, the pill names the state in text.
 */
import {
  CheckCircle2,
  CircleDashed,
  Clock,
  Eye,
  Timer,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";

export type ColumnState = "backlog" | "in_progress" | "review" | "done";

interface PillStyle {
  icon: LucideIcon;
  label: string;
  className: string;
}

const STYLES: Record<ColumnState, PillStyle> = {
  backlog: {
    icon: CircleDashed,
    label: "Backlog",
    className: "border-border bg-muted/50 text-muted-foreground",
  },
  in_progress: {
    icon: Timer,
    label: "In progress",
    className: "border-info/40 bg-info/10 text-info",
  },
  review: {
    icon: Eye,
    label: "Review",
    className: "border-warning/40 bg-warning/10 text-warning",
  },
  done: {
    icon: CheckCircle2,
    label: "Done",
    className: "border-success/40 bg-success/10 text-success",
  },
};

export function StatusPill({
  state,
  className,
}: {
  state: ColumnState | string;
  className?: string;
}) {
  const style =
    state in STYLES
      ? STYLES[state as ColumnState]
      : ({
          icon: Clock,
          label: state,
          className: "border-border bg-muted/50 text-muted-foreground",
        } satisfies PillStyle);
  const Icon = style.icon;
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1 rounded-full border px-2 text-[10px] font-medium uppercase tracking-wider",
        style.className,
        className,
      )}
    >
      <Icon className="h-3 w-3" />
      <span>{style.label}</span>
    </span>
  );
}
