/**
 * Workspace header — name + status pills + 4 live actions (S7).
 *
 * Wires (ADR-007 §4 S7):
 *   - Switch  : DropdownMenu of active workspaces → router push
 *   - Edit    : opens the project-meta dialog (parent-owned)
 *   - Pause   : POST /api/projects/{slug}/autopilot/(pause|resume)
 *               via parent handler; flips label on autopilotPaused
 *   - Archive : POST /api/projects/{slug}/(archive|unarchive)
 *               via parent handler; AlertDialog confirm lives at
 *               the parent so the destructive double-tap is explicit.
 *
 * State surfacing pills (autopilot paused / archived) make the workspace
 * status legible at a glance without consulting the Pause button label.
 */
"use client";

import { useEffect, useState } from "react";
import { Archive, ArchiveRestore, ChevronDown, Edit2, Pause, Play } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { listProjects, type ProjectResponse } from "@/lib/api";

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
  slug: string;
  name: string;
  status: ProjectStatus;
  meta: string;
  autopilotPaused: boolean;
  archived: boolean;
  onPauseToggle?: () => void;
  pausing?: boolean;
  onEdit?: () => void;
  onArchiveToggle?: () => void;
  archiving?: boolean;
  onSwitchWorkspace?: (slug: string) => void;
}

export function WorkspaceHeader({
  slug,
  name,
  status,
  meta,
  autopilotPaused,
  archived,
  onPauseToggle,
  pausing,
  onEdit,
  onArchiveToggle,
  archiving,
  onSwitchWorkspace,
}: WorkspaceHeaderProps) {
  const m = STATUS_META[status];
  const [switchOpen, setSwitchOpen] = useState(false);
  const [projects, setProjects] = useState<ProjectResponse[] | null>(null);

  // Refetch on every open so archive / unarchive elsewhere doesn't
  // leave the dropdown showing stale rows (audit-god S7 Finding #5,
  // 2026-05-24). The fetch is cheap and the operator only sees it
  // when they explicitly click Switch.
  useEffect(() => {
    if (!switchOpen) return;
    let cancelled = false;
    setProjects(null);
    listProjects()
      .then((rows) => {
        if (!cancelled) setProjects(rows);
      })
      .catch(() => {
        if (!cancelled) setProjects([]);
      });
    return () => {
      cancelled = true;
    };
  }, [switchOpen]);

  const pauseLabel = pausing
    ? "…"
    : autopilotPaused
      ? "Resume Self Jr"
      : "Pause Self Jr";

  const archiveLabel = archiving
    ? "…"
    : archived
      ? "Unarchive"
      : "Archive";

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
        {autopilotPaused && (
          <span className="px-3 py-1 bg-amber-100 text-amber-800 rounded-full text-caption flex items-center gap-1.5 font-bold uppercase tracking-tight">
            <Pause className="h-3 w-3" strokeWidth={2} />
            Paused
          </span>
        )}
        {archived && (
          <span className="px-3 py-1 bg-surface-container-high text-on-surface-variant rounded-full text-caption flex items-center gap-1.5 font-bold uppercase tracking-tight">
            <Archive className="h-3 w-3" strokeWidth={2} />
            Archived
          </span>
        )}
        <span className="text-on-surface-variant text-caption border-l border-outline-variant pl-3 ml-1">
          {meta}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <DropdownMenu open={switchOpen} onOpenChange={setSwitchOpen}>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="px-4 py-2 text-on-surface-variant hover:bg-surface-container rounded-lg text-caption font-medium transition-colors flex items-center gap-1"
            >
              Switch
              <ChevronDown className="h-4 w-4" strokeWidth={1.75} />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-[14rem]">
            <DropdownMenuLabel>Workspaces</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {projects === null && (
              <DropdownMenuItem disabled>
                <span className="text-on-surface-variant">Loading…</span>
              </DropdownMenuItem>
            )}
            {projects !== null && projects.length === 0 && (
              <DropdownMenuItem disabled>
                <span className="text-on-surface-variant">
                  No workspaces yet.
                </span>
              </DropdownMenuItem>
            )}
            {projects !== null &&
              projects.map((p) => {
                const isCurrent = p.slug === slug;
                return (
                  <DropdownMenuItem
                    key={p.slug}
                    onSelect={(e) => {
                      if (isCurrent) {
                        e.preventDefault();
                        return;
                      }
                      onSwitchWorkspace?.(p.slug);
                    }}
                    className={isCurrent ? "opacity-60" : ""}
                  >
                    <div className="flex flex-col flex-1">
                      <span
                        className={
                          isCurrent
                            ? "font-bold text-on-surface"
                            : "text-on-surface"
                        }
                      >
                        {p.name}
                      </span>
                      <span className="text-[10px] text-on-surface-variant tabular-nums">
                        {p.slug}
                        {isCurrent ? " · current" : ""}
                      </span>
                    </div>
                  </DropdownMenuItem>
                );
              })}
          </DropdownMenuContent>
        </DropdownMenu>

        <button
          type="button"
          onClick={onEdit}
          disabled={!onEdit || archived}
          className="px-4 py-2 text-on-surface-variant hover:bg-surface-container rounded-lg text-caption font-medium transition-colors flex items-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Edit2 className="h-4 w-4" strokeWidth={1.75} />
          Edit
        </button>

        <button
          type="button"
          onClick={onPauseToggle}
          disabled={!onPauseToggle || pausing || archived}
          className="px-4 py-2 border border-outline-variant text-on-surface hover:bg-surface-container-high rounded-lg text-caption font-medium transition-colors flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {autopilotPaused ? (
            <Play className="h-4 w-4" strokeWidth={1.75} />
          ) : (
            <Pause className="h-4 w-4" strokeWidth={1.75} />
          )}
          {pauseLabel}
        </button>

        <button
          type="button"
          onClick={onArchiveToggle}
          disabled={!onArchiveToggle || archiving}
          className="px-4 py-2 text-on-surface-variant hover:bg-surface-container rounded-lg text-caption font-medium transition-colors flex items-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {archived ? (
            <ArchiveRestore className="h-4 w-4" strokeWidth={1.75} />
          ) : (
            <Archive className="h-4 w-4" strokeWidth={1.75} />
          )}
          {archiveLabel}
        </button>
      </div>
    </section>
  );
}
