import { ChevronDown, type LucideIcon } from "lucide-react";

import type { ProjectStatus } from "@/components/dashboard/project-card";

const STATUS_META: Record<
  ProjectStatus,
  { label: string; pillClass: string; dotClass: string }
> = {
  shipping: {
    label: "Shipping",
    pillClass: "bg-primary/10 text-primary",
    dotClass: "bg-primary",
  },
  sleeping: {
    label: "Sleeping",
    pillClass: "bg-amber-50 text-amber-700",
    dotClass: "bg-amber-500",
  },
  pending: {
    label: "Pending Approval",
    pillClass: "bg-amber-50 text-amber-700",
    dotClass: "bg-amber-500",
  },
  errored: {
    label: "Errored",
    pillClass: "bg-red-50 text-red-700",
    dotClass: "bg-error",
  },
};

export interface WorkspaceHeaderProps {
  name: string;
  status: ProjectStatus;
  meta: string; // e.g. "12/24 tasks · last activity 2m ago"
  onPause?: () => void;
  pausing?: boolean;
}

interface ActionButton {
  label: string;
  variant: "ghost" | "outline";
  onClick?: () => void;
  Icon?: LucideIcon;
}

export function WorkspaceHeader({
  name,
  status,
  meta,
  onPause,
  pausing,
}: WorkspaceHeaderProps) {
  const m = STATUS_META[status];
  const actions: ActionButton[] = [
    { label: "Switch", variant: "ghost" },
    { label: "Edit", variant: "ghost" },
    {
      label: pausing ? "Pausing…" : "Pause Self Jr",
      variant: "outline",
      onClick: onPause,
    },
    { label: "Archive", variant: "ghost" },
  ];

  return (
    <section className="sticky top-topbar-height bg-surface z-30 border-b border-outline-variant -mx-gutter-desktop px-gutter-desktop py-4 flex items-center justify-between flex-wrap gap-3">
      <div className="flex items-center gap-3 flex-wrap">
        <h2 className="font-display text-display text-on-surface">{name}</h2>
        <span
          className={`${m.pillClass} px-3 py-1 rounded-full text-caption flex items-center gap-1.5 font-bold uppercase tracking-tight`}
        >
          <span className={`w-2 h-2 rounded-full ${m.dotClass}`} />
          {m.label}
        </span>
        <span className="text-on-surface-variant text-caption border-l border-outline-variant pl-3 ml-1">
          {meta}
        </span>
      </div>
      <div className="flex items-center gap-2">
        {actions.map((a) => (
          <button
            key={a.label}
            type="button"
            onClick={a.onClick}
            className={
              a.variant === "outline"
                ? "px-4 py-2 border border-outline-variant text-on-surface hover:bg-surface-container-high rounded-lg text-caption font-medium transition-colors"
                : "px-4 py-2 text-on-surface-variant hover:bg-surface-container rounded-lg text-caption font-medium transition-colors flex items-center gap-1"
            }
          >
            {a.label}
            {a.label === "Switch" && (
              <ChevronDown className="h-4 w-4" strokeWidth={1.75} />
            )}
          </button>
        ))}
      </div>
    </section>
  );
}
