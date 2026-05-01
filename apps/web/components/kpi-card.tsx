/**
 * KPI card — labelled metric tile for the dashboard top strip.
 *
 * Designed for tabular alignment in a 4-column grid. Always renders
 * even when data is unknown — we show a "—" placeholder rather than
 * hide the tile, so the layout doesn't shuffle as data loads.
 */
import { type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

interface KpiCardProps {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon: LucideIcon;
  /** Optional accent — color coding hooks into the same palette as StatusBadge. */
  tone?: "default" | "success" | "warning" | "danger" | "info";
  className?: string;
}

const TONE: Record<NonNullable<KpiCardProps["tone"]>, string> = {
  default: "border-border bg-card",
  success: "border-success/30 bg-success/5",
  warning: "border-warning/30 bg-warning/5",
  danger: "border-destructive/30 bg-destructive/5",
  info: "border-info/30 bg-info/5",
};

const ICON_TONE: Record<NonNullable<KpiCardProps["tone"]>, string> = {
  default: "text-muted-foreground",
  success: "text-success",
  warning: "text-warning",
  danger: "text-destructive",
  info: "text-info",
};

export function KpiCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = "default",
  className,
}: KpiCardProps) {
  return (
    <div
      className={cn(
        "flex flex-col rounded-lg border p-4 shadow-sm",
        TONE[tone],
        className,
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
        <Icon className={cn("h-4 w-4", ICON_TONE[tone])} />
      </div>
      <span className="mt-2 font-mono text-2xl font-semibold tabular-nums tracking-tight">
        {value}
      </span>
      {hint ? (
        <span className="mt-1 truncate text-[11px] text-muted-foreground">
          {hint}
        </span>
      ) : null}
    </div>
  );
}
