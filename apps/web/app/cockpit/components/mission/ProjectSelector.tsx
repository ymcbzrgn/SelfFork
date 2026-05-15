/**
 * Project selector — Mission tab — Order 6.
 *
 * Plain native ``<select>`` so the cockpit doesn't ship a heavy
 * combobox primitive for what is, in practice, a 5-10 item list.
 */
"use client";

import type { ProjectResponse } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";

interface Props {
  projects: ProjectResponse[];
  activeSlug: string | null;
  loading: boolean;
  onChange: (slug: string | null) => void;
}

export function ProjectSelector({
  projects,
  activeSlug,
  loading,
  onChange,
}: Props) {
  if (loading) {
    return <Skeleton className="h-9 w-72" />;
  }
  if (projects.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No projects yet. Create one from{" "}
        <code className="font-mono">selffork project create &lt;name&gt;</code>{" "}
        or the dashboard's Projects page.
      </p>
    );
  }
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">Project</span>
      <select
        aria-label="Active project"
        value={activeSlug ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
        className="rounded-md border border-border bg-card px-2 py-1 text-sm"
      >
        {projects.map((p) => (
          <option key={p.slug} value={p.slug}>
            {p.name} ({p.slug})
          </option>
        ))}
      </select>
    </label>
  );
}
